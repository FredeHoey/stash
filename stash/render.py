from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateSyntaxError,
    UndefinedError,
    select_autoescape,
)

from stash.repositories import DotfileModuleRepository, RenderedFileRepository


@dataclass(frozen=True)
class RenderedPayload:
    rendered_path: Path
    template_path: Path
    content: str
    content_hash: str


def hex_color(value):
    return f"#{value}"


def render_dotfiles(
    module: Path,
    module_name: str,
    target: Path,
    variables: dict[str, Any],
    render_root: Path,
    generation_id: UUID,
    module_repo: DotfileModuleRepository,
    rendered_file_repo: RenderedFileRepository,
) -> bool:
    render_path = render_root / module_name / str(generation_id)

    files = [file for file in module.rglob("*") if file.is_file()]
    env = Environment(
        loader=FileSystemLoader(module),
        autoescape=select_autoescape(),
        undefined=StrictUndefined,
    )

    env.filters["hex_color"] = hex_color

    existing_module = module_repo.get_latest_by_module_name(module_name)
    existing_hashes: dict[Path, str] = {}
    if existing_module is not None:
        existing_hashes = rendered_file_repo.get_by_module_with_hashes(
            existing_module.id
        )
        existing_hashes = {
            path.relative_to(existing_module.output_path): value
            for path, value in existing_hashes.items()
        }

    rendered_payloads: list[RenderedPayload] = []

    for file in files:
        template_name = file.relative_to(module).as_posix()
        template = env.get_template(template_name)
        try:
            rendered = template.render(variables)
        except UnicodeDecodeError:
            print(f"Skipping non-text template: {module / template_name}")
            continue
        except TemplateSyntaxError as e:
            print(f"{e.message}")
            continue
        except UndefinedError as e:
            print(f"Missing variable: {e.message} in {module / template_name}")
            break

        rendered_name = file.name.replace("dot_", ".")
        rendered_file = render_path / template_name
        if file.name.startswith("dot_"):
            rendered_file = rendered_file.with_name(rendered_name)
        rendered_abs = rendered_file.resolve()
        template_abs = file.resolve()
        content_hash = sha256(rendered.encode()).hexdigest()
        rendered_payloads.append(
            RenderedPayload(rendered_abs, template_abs, rendered, content_hash)
        )

    if not rendered_payloads:
        return False

    current_hashes = {
        payload.rendered_path.relative_to(render_path): payload.content_hash
        for payload in rendered_payloads
    }
    if existing_hashes and existing_hashes == current_hashes:
        return False

    render_path.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)

    module_record = module_repo.create(
        generation_id=generation_id,
        module_name=module_name,
        output_path=render_path.resolve(),
        target_path=target.resolve(),
    )

    for payload in rendered_payloads:
        payload.rendered_path.parent.mkdir(parents=True, exist_ok=True)
        payload.rendered_path.write_text(payload.content)
        rendered_file_repo.create(
            module_id=module_record.id,
            file_path=payload.rendered_path.as_posix(),
            template_path=payload.template_path.as_posix(),
            content_hash=payload.content_hash,
        )

        relative_target = payload.rendered_path.relative_to(render_path)
        link_path = target / relative_target
        if link_path.exists():
            if link_path.is_dir() and not link_path.is_symlink():
                raise IsADirectoryError(
                    f"Cannot replace directory at {link_path} with a symlink"
                )
            link_path.unlink()
        link_path.parent.mkdir(parents=True, exist_ok=True)
        temp_link = link_path.with_name(f"{link_path.name}.tmp")
        if temp_link.exists():
            temp_link.unlink()
        temp_link.symlink_to(payload.rendered_path)
        temp_link.replace(link_path)

    return True

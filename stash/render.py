from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from stash.deployment import atomic_symlink
from stash.repositories import DotfileModuleRepository, RenderedFileRepository
from stash.templates import TemplateRenderError, render_templates


def render_dotfiles(
    module: Path,
    module_name: str,
    target: Path,
    variables: dict[str, Any],
    render_root: Path,
    generation_id: UUID,
    module_repo: DotfileModuleRepository,
    rendered_file_repo: RenderedFileRepository,
    config_hash: str | None = None,
) -> bool:
    render_path = render_root / module_name / str(generation_id)

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

    try:
        rendered_templates = render_templates(module, variables)
    except TemplateRenderError as exc:
        print(str(exc))
        return False

    if not rendered_templates:
        return False

    current_hashes = {
        template.relative_path: template.content_hash for template in rendered_templates
    }
    if (
        existing_hashes
        and existing_hashes == current_hashes
        and existing_module is not None
        and existing_module.config_hash == config_hash
    ):
        return False

    render_path.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)

    module_record = module_repo.create(
        generation_id=generation_id,
        module_name=module_name,
        output_path=render_path.resolve(),
        target_path=target.resolve(),
        config_hash=config_hash,
    )

    for template in rendered_templates:
        rendered_path = (render_path / template.relative_path).resolve()
        rendered_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_path.write_text(template.content)
        rendered_file_repo.create(
            module_id=module_record.id,
            file_path=rendered_path.as_posix(),
            template_path=template.template_path.as_posix(),
            content_hash=template.content_hash,
        )

        atomic_symlink(target / template.relative_path, rendered_path)

    return True

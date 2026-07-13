from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)


class TemplateRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedTemplate:
    relative_path: Path
    template_path: Path
    content: str
    content_hash: str


def hex_color(value: Any) -> str:
    return f"#{value}"


def template_environment(root: Path) -> Environment:
    environment = Environment(
        loader=FileSystemLoader(root),
        autoescape=select_autoescape(),
        undefined=StrictUndefined,
    )
    environment.filters["hex_color"] = hex_color
    return environment


def render_templates(
    module: Path,
    variables: dict[str, Any],
) -> list[RenderedTemplate]:
    environment = template_environment(module)
    rendered_templates: list[RenderedTemplate] = []

    for template_path in sorted(path for path in module.rglob("*") if path.is_file()):
        template_name = template_path.relative_to(module).as_posix()
        try:
            rendered = environment.get_template(template_name).render(variables)
        except UnicodeDecodeError:
            print(f"Skipping non-text template: {template_path}")
            continue
        except TemplateError as exc:
            raise TemplateRenderError(
                f"Could not render {template_path}: {exc}"
            ) from exc

        relative_path = Path(template_name)
        if template_path.name.startswith("dot_"):
            relative_path = relative_path.with_name(
                template_path.name.replace("dot_", ".")
            )
        rendered_templates.append(
            RenderedTemplate(
                relative_path=relative_path,
                template_path=template_path.resolve(),
                content=rendered,
                content_hash=sha256(rendered.encode()).hexdigest(),
            )
        )

    return rendered_templates

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
    select_autoescape,
)
from jinja2 import meta


class TemplateRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TemplateMetadata:
    template_name: str
    relative_path: Path
    variable_names: frozenset[str]
    dependency_names: frozenset[str]
    has_dynamic_dependencies: bool


@dataclass(frozen=True)
class RenderedTemplate:
    metadata: TemplateMetadata
    content: str


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


def template_output_path(template_name: str) -> Path:
    relative_path = Path(template_name)
    if relative_path.name.startswith("dot_"):
        return relative_path.with_name(relative_path.name.replace("dot_", ".", 1))
    return relative_path


def template_metadata(module: Path) -> dict[str, TemplateMetadata]:
    environment = template_environment(module)
    templates: dict[str, TemplateMetadata] = {}

    for template_path in sorted(path for path in module.rglob("*") if path.is_file()):
        template_name = template_path.relative_to(module).as_posix()
        try:
            source = template_path.read_text()
            parsed = environment.parse(source)
        except UnicodeDecodeError:
            print(f"Skipping non-text template: {template_path}")
            continue
        except TemplateError as exc:
            raise TemplateRenderError(
                f"Could not inspect {template_path}: {exc}"
            ) from exc

        dependency_names: set[str] = set()
        has_dynamic_dependencies = False
        for dependency in meta.find_referenced_templates(parsed) or ():
            if dependency is None:
                has_dynamic_dependencies = True
                continue
            dependency_names.add(dependency)

        templates[template_name] = TemplateMetadata(
            template_name=template_name,
            relative_path=template_output_path(template_name),
            variable_names=frozenset(meta.find_undeclared_variables(parsed)),
            dependency_names=frozenset(dependency_names),
            has_dynamic_dependencies=has_dynamic_dependencies,
        )

    return templates


def render_templates(
    module: Path,
    variables: dict[str, Any],
    selected: set[str] | None = None,
) -> list[RenderedTemplate]:
    environment = template_environment(module)
    templates = template_metadata(module)
    template_names = sorted(selected or templates)
    rendered_templates: list[RenderedTemplate] = []

    for template_name in template_names:
        metadata = templates.get(template_name)
        if metadata is None:
            continue
        try:
            content = environment.get_template(template_name).render(variables)
        except TemplateError as exc:
            raise TemplateRenderError(
                f"Could not render {module / template_name}: {exc}"
            ) from exc
        rendered_templates.append(RenderedTemplate(metadata, content))

    return rendered_templates

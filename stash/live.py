from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

from stash.config import module_target, template_variables
from stash.deployment import atomic_symlink
from stash.templates import (
    RenderedTemplate,
    TemplateMetadata,
    TemplateRenderError,
    render_templates,
    template_metadata,
)


class DaemonError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveTemplate:
    module_name: str
    source_path: Path
    template_name: str
    relative_path: Path
    link_path: Path
    variable_names: frozenset[str]
    dependency_names: frozenset[str]
    has_dynamic_dependencies: bool


@dataclass(frozen=True)
class LiveState:
    active_links: frozenset[Path]
    module_names: frozenset[str]
    source_paths: frozenset[Path]
    module_targets: dict[str, Path]
    templates: dict[Path, LiveTemplate]


def _points_into(path: Path, root: Path) -> bool:
    if not path.is_symlink():
        return False
    return path.resolve(strict=False).is_relative_to(root.resolve())


def _remove_live_link(path: Path, live_root: Path) -> None:
    if _points_into(path, live_root):
        path.unlink()


def _remove_empty_directories(path: Path, stop: Path) -> None:
    current = path
    while current != stop and current.exists():
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _write_live_file(live_path: Path, content: str) -> None:
    live_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = live_path.with_name(f".{live_path.name}.tmp")
    temporary_path.write_text(content)
    temporary_path.replace(live_path)


def _load_module_templates(source: Path) -> dict[str, TemplateMetadata]:
    if not source.is_dir():
        raise DaemonError(f"Dotfile module does not exist: {source}")
    try:
        templates = template_metadata(source)
    except TemplateRenderError as exc:
        raise DaemonError(str(exc)) from exc
    if not templates:
        raise DaemonError(f"Dotfile module has no text templates: {source}")
    return templates


def _render_module_templates(
    source: Path,
    variables: dict[str, Any],
    selected: set[str] | None = None,
) -> list[RenderedTemplate]:
    try:
        return render_templates(source, variables, selected)
    except TemplateRenderError as exc:
        raise DaemonError(str(exc)) from exc


def _template_state(
    module_name: str,
    source_path: Path,
    target_path: Path,
    metadata: TemplateMetadata,
) -> LiveTemplate:
    return LiveTemplate(
        module_name=module_name,
        source_path=source_path,
        template_name=metadata.template_name,
        relative_path=metadata.relative_path,
        link_path=target_path / metadata.relative_path,
        variable_names=metadata.variable_names,
        dependency_names=metadata.dependency_names,
        has_dynamic_dependencies=metadata.has_dynamic_dependencies,
    )


def _state_from_modules(
    modules: dict[str, dict[str, Any]],
    dotfiles: Path,
    live_root: Path,
    variables: dict[str, Any],
) -> LiveState:
    templates: dict[Path, LiveTemplate] = {}
    module_targets: dict[str, Path] = {}

    for module_name, module_config in modules.items():
        if not isinstance(module_name, str) or not isinstance(module_config, dict):
            raise DaemonError("Every dotfile module must be a mapping")
        source = (dotfiles / module_name).resolve()
        target = module_target(module_name, module_config)
        module_targets[module_name] = target
        metadata_by_name = _load_module_templates(source)
        rendered_templates = _render_module_templates(
            source,
            variables,
            set(metadata_by_name),
        )
        for rendered in rendered_templates:
            live_path = live_root / module_name / rendered.metadata.relative_path
            _write_live_file(live_path, rendered.content)
            atomic_symlink(target / rendered.metadata.relative_path, live_path)
        for metadata in metadata_by_name.values():
            template_path = source / metadata.template_name
            templates[template_path] = _template_state(
                module_name, source, target, metadata
            )

    return LiveState(
        active_links=frozenset(template.link_path for template in templates.values()),
        module_names=frozenset(modules),
        source_paths=frozenset((dotfiles / name).resolve() for name in modules),
        module_targets=module_targets,
        templates=templates,
    )


def _module_templates(
    templates: dict[Path, LiveTemplate],
    module_name: str,
) -> dict[str, LiveTemplate]:
    return {
        template.template_name: template
        for template in templates.values()
        if template.module_name == module_name
    }


def _module_reverse_dependencies(
    old_templates: dict[str, LiveTemplate],
    new_templates: dict[str, TemplateMetadata],
) -> dict[str, set[str]]:
    reverse_dependencies: dict[str, set[str]] = {
        name: set() for name in set(old_templates) | set(new_templates)
    }
    has_dynamic_dependencies = any(
        template.has_dynamic_dependencies for template in old_templates.values()
    ) or any(template.has_dynamic_dependencies for template in new_templates.values())
    if has_dynamic_dependencies:
        names = set(reverse_dependencies)
        return {name: set(names) for name in names}

    for name, template in old_templates.items():
        for dependency in template.dependency_names:
            reverse_dependencies.setdefault(dependency, set()).add(name)
    for name, template in new_templates.items():
        for dependency in template.dependency_names:
            reverse_dependencies.setdefault(dependency, set()).add(name)
    return reverse_dependencies


def _affected_template_names(
    old_templates: dict[str, LiveTemplate],
    new_templates: dict[str, TemplateMetadata],
    changed_names: set[str],
    changed_variables: set[str],
    target_changed: bool,
) -> set[str]:
    affected = set(changed_names)
    if target_changed:
        affected.update(new_templates)
    if changed_variables:
        affected.update(
            name
            for name, template in old_templates.items()
            if not changed_variables.isdisjoint(template.variable_names)
        )
    reverse_dependencies = _module_reverse_dependencies(old_templates, new_templates)
    pending = list(affected)
    while pending:
        name = pending.pop()
        for dependent in reverse_dependencies.get(name, ()):
            if dependent in affected:
                continue
            affected.add(dependent)
            pending.append(dependent)
    return affected


def _rebuild_state(
    previous_state: LiveState,
    modules: dict[str, dict[str, Any]],
    dotfiles: Path,
    new_metadata: dict[str, dict[str, TemplateMetadata]],
) -> LiveState:
    templates = {
        path: template
        for path, template in previous_state.templates.items()
        if template.module_name in modules and template.module_name not in new_metadata
    }
    module_targets = {
        module_name: module_target(module_name, module_config)
        for module_name, module_config in modules.items()
        if isinstance(module_name, str) and isinstance(module_config, dict)
    }

    for module_name, metadata_by_name in new_metadata.items():
        source = (dotfiles / module_name).resolve()
        target = module_targets[module_name]
        for metadata in metadata_by_name.values():
            template_path = source / metadata.template_name
            templates[template_path] = _template_state(
                module_name, source, target, metadata
            )

    return LiveState(
        active_links=frozenset(template.link_path for template in templates.values()),
        module_names=frozenset(module_targets),
        source_paths=frozenset((dotfiles / name).resolve() for name in module_targets),
        module_targets=module_targets,
        templates=templates,
    )


def _module_changes(
    previous_state: LiveState,
    modules: dict[str, dict[str, Any]],
    dotfiles: Path,
    changed_paths: set[Path],
    changed_variables: set[str],
) -> tuple[dict[str, set[str]], dict[str, dict[str, TemplateMetadata]], set[str]]:
    affected_names: dict[str, set[str]] = {}
    new_metadata: dict[str, dict[str, TemplateMetadata]] = {}
    removed_modules = previous_state.module_names - set(modules)
    current_modules = {
        module_name
        for module_name, module_config in modules.items()
        if isinstance(module_name, str) and isinstance(module_config, dict)
    }

    if current_modules != previous_state.module_names:
        return {name: set() for name in current_modules}, {}, removed_modules

    for module_name in current_modules:
        source = (dotfiles / module_name).resolve()
        old_templates = _module_templates(previous_state.templates, module_name)
        changed_names = {
            path.relative_to(source).as_posix()
            for path in changed_paths
            if path.is_relative_to(source) and not path.is_dir()
        }
        target_changed = (
            module_target(module_name, modules[module_name])
            != previous_state.module_targets[module_name]
        )
        if changed_names or target_changed:
            metadata_by_name = _load_module_templates(source)
            new_metadata[module_name] = metadata_by_name
        else:
            metadata_by_name = {
                name: TemplateMetadata(
                    template_name=template.template_name,
                    relative_path=template.relative_path,
                    variable_names=template.variable_names,
                    dependency_names=template.dependency_names,
                    has_dynamic_dependencies=template.has_dynamic_dependencies,
                )
                for name, template in old_templates.items()
            }
        relevant_names = set(old_templates) | set(metadata_by_name)
        names = _affected_template_names(
            old_templates,
            metadata_by_name,
            (changed_names & relevant_names)
            | (set(old_templates) - set(metadata_by_name)),
            changed_variables,
            target_changed,
        )
        if names:
            affected_names[module_name] = names
        if module_name in new_metadata:
            continue
        if changed_variables:
            new_metadata[module_name] = metadata_by_name

    return affected_names, new_metadata, removed_modules


def render_live(
    config: dict[str, Any],
    dotfiles: Path,
    live_root: Path,
    previous_state: LiveState | None = None,
    theme_name: str | None = None,
    changed_paths: set[Path] | None = None,
    changed_variables: set[str] | None = None,
) -> LiveState:
    modules = config.get("dotfiles")
    if not isinstance(modules, dict):
        raise DaemonError("Config must contain a 'dotfiles' mapping")

    try:
        variables = template_variables(config, dotfiles, theme_name)
    except ValueError as exc:
        raise DaemonError(str(exc)) from exc

    live_root.mkdir(parents=True, exist_ok=True)
    if previous_state is None:
        return _state_from_modules(modules, dotfiles, live_root, variables)

    if changed_paths is None and changed_variables is None:
        for template in previous_state.templates.values():
            _remove_live_link(template.link_path, live_root)
        for module_name in previous_state.module_names:
            stale_path = live_root / module_name
            if stale_path.exists():
                shutil.rmtree(stale_path)
        return _state_from_modules(modules, dotfiles, live_root, variables)

    if changed_paths is None:
        changed_paths = set()
    if changed_variables is None:
        changed_variables = set()

    affected_names, new_metadata, removed_modules = _module_changes(
        previous_state,
        modules,
        dotfiles,
        changed_paths,
        changed_variables,
    )
    if set(modules) != previous_state.module_names:
        for template in previous_state.templates.values():
            _remove_live_link(template.link_path, live_root)
        for module_name in previous_state.module_names:
            stale_path = live_root / module_name
            if stale_path.exists():
                shutil.rmtree(stale_path)
        return _state_from_modules(modules, dotfiles, live_root, variables)
    if not affected_names and not removed_modules:
        return previous_state

    rendered_by_module: dict[str, list[RenderedTemplate]] = {}
    for module_name, names in affected_names.items():
        source = (dotfiles / module_name).resolve()
        current_names = names & set(new_metadata[module_name])
        if current_names:
            rendered_by_module[module_name] = _render_module_templates(
                source,
                variables,
                current_names,
            )

    next_state = _rebuild_state(previous_state, modules, dotfiles, new_metadata)

    for module_name in removed_modules:
        for template in _module_templates(
            previous_state.templates, module_name
        ).values():
            _remove_live_link(template.link_path, live_root)
        stale_path = live_root / module_name
        if stale_path.exists():
            shutil.rmtree(stale_path)

    for module_name, names in affected_names.items():
        old_templates = _module_templates(previous_state.templates, module_name)
        new_templates = _module_templates(next_state.templates, module_name)
        rendered = {
            template.metadata.template_name: template
            for template in rendered_by_module.get(module_name, [])
        }

        for name in names - set(new_templates):
            old_template = old_templates[name]
            _remove_live_link(old_template.link_path, live_root)
            live_path = live_root / module_name / old_template.relative_path
            if live_path.exists():
                live_path.unlink()
                _remove_empty_directories(live_path.parent, live_root / module_name)

        for name, template in new_templates.items():
            old_template = old_templates.get(name)
            if old_template is None:
                continue
            if old_template.link_path != template.link_path:
                _remove_live_link(old_template.link_path, live_root)

        for name, template in rendered.items():
            live_path = live_root / module_name / template.metadata.relative_path
            _write_live_file(live_path, template.content)
            atomic_symlink(new_templates[name].link_path, live_path)

    return next_state

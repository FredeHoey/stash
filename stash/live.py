from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

from stash.config import module_target, template_variables
from stash.db import get_session
from stash.deployment import atomic_symlink
from stash.repositories import DotfileModuleRepository, RenderedFileRepository
from stash.templates import TemplateRenderError, render_templates


class DaemonError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveState:
    active_links: frozenset[Path]
    managed_links: frozenset[Path]
    module_names: frozenset[str]
    source_paths: frozenset[Path]


def _points_into(path: Path, root: Path) -> bool:
    if not path.is_symlink():
        return False
    return path.resolve(strict=False).is_relative_to(root.resolve())


def _remove_live_link(path: Path, live_root: Path) -> None:
    if _points_into(path, live_root):
        path.unlink()


def _stage_module(
    source: Path,
    staging_path: Path,
    variables: dict[str, Any],
) -> list[Path]:
    if not source.is_dir():
        raise DaemonError(f"Dotfile module does not exist: {source}")

    try:
        templates = render_templates(source, variables)
    except TemplateRenderError as exc:
        raise DaemonError(str(exc)) from exc

    for template in templates:
        output_path = staging_path / template.relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(template.content)

    if not templates:
        raise DaemonError(f"Dotfile module has no text templates: {source}")
    return [template.relative_path for template in templates]


def _replace_directory(staging_path: Path, live_path: Path) -> None:
    previous_path = live_path.with_name(f".{live_path.name}.previous")
    if previous_path.exists():
        shutil.rmtree(previous_path)
    if live_path.exists():
        live_path.rename(previous_path)
    staging_path.rename(live_path)
    if previous_path.exists():
        shutil.rmtree(previous_path)


def render_live(
    config: dict[str, Any],
    dotfiles: Path,
    live_root: Path,
    previous_state: LiveState | None = None,
) -> LiveState:
    modules = config.get("dotfiles")
    if not isinstance(modules, dict):
        raise DaemonError("Config must contain a 'dotfiles' mapping")

    try:
        variables = template_variables(config, dotfiles)
    except ValueError as exc:
        raise DaemonError(str(exc)) from exc

    live_root.mkdir(parents=True, exist_ok=True)
    staging_root = live_root / ".staging"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    staging_root.mkdir()

    plans: dict[str, tuple[Path, list[Path]]] = {}
    source_paths: set[Path] = set()
    try:
        for module_name, module_config in modules.items():
            if not isinstance(module_name, str) or not isinstance(module_config, dict):
                raise DaemonError("Every dotfile module must be a mapping")
            source = (dotfiles / module_name).resolve()
            source_paths.add(source)
            relative_paths = _stage_module(
                source,
                staging_root / module_name,
                variables,
            )
            plans[module_name] = (
                module_target(module_name, module_config),
                relative_paths,
            )
    except Exception:
        shutil.rmtree(staging_root)
        raise

    for module_name in plans:
        _replace_directory(staging_root / module_name, live_root / module_name)
    shutil.rmtree(staging_root)

    desired_links: set[Path] = set()
    for module_name, (target, relative_paths) in plans.items():
        for relative_path in relative_paths:
            link_path = target / relative_path
            atomic_symlink(link_path, live_root / module_name / relative_path)
            desired_links.add(link_path)

    old_links = previous_state.active_links if previous_state else frozenset()
    for stale_link in old_links - desired_links:
        _remove_live_link(stale_link, live_root)

    old_modules = previous_state.module_names if previous_state else frozenset()
    for stale_module in old_modules - plans.keys():
        stale_path = live_root / stale_module
        if stale_path.exists():
            shutil.rmtree(stale_path)

    managed_links = set(previous_state.managed_links if previous_state else ())
    managed_links.update(desired_links)
    module_names = set(old_modules)
    module_names.update(plans)
    return LiveState(
        active_links=frozenset(desired_links),
        managed_links=frozenset(managed_links),
        module_names=frozenset(module_names),
        source_paths=frozenset(source_paths),
    )


def restore_latest(
    state: LiveState,
    live_root: Path,
    db_path: Path | None = None,
) -> None:
    for link_path in state.managed_links:
        _remove_live_link(link_path, live_root)

    with get_session(db_path) as session:
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)
        for module_name in state.module_names:
            module = module_repo.get_latest_by_module_name(module_name)
            if module is None:
                continue
            if not module.output_path.is_dir():
                print(
                    f"Cannot restore {module_name}: rendered directory is missing: "
                    f"{module.output_path}"
                )
                continue
            for rendered_file in rendered_file_repo.get_by_module(module.id):
                relative_path = rendered_file.file_path.relative_to(module.output_path)
                if not rendered_file.file_path.exists():
                    print(
                        f"Cannot restore missing rendered file: {rendered_file.file_path}"
                    )
                    continue
                atomic_symlink(
                    module.target_path / relative_path,
                    rendered_file.file_path,
                )

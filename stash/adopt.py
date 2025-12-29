from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable
from uuid import UUID

from stash.render import render_dotfiles
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)


def common_path(paths: Iterable[Path]) -> Path:
    resolved = [path.expanduser().resolve() for path in paths]
    if not resolved:
        raise ValueError("No paths provided")
    common = Path(os.path.commonpath([str(path) for path in resolved]))
    if common.is_file():
        return common.parent
    return common


def normalize_module_name(raw_name: str) -> str:
    if not raw_name.strip():
        raise ValueError("Module name cannot be empty")
    return raw_name.strip()


def to_module_filename(path: Path) -> str:
    if path.name.startswith("."):
        return f"dot_{path.name[1:]}"
    return path.name


def ensure_parent_dir(paths: list[Path]) -> Path:
    base_path = common_path(paths)
    if base_path == Path(""):
        raise ValueError("Cannot determine common path")
    for path in paths:
        try:
            path.relative_to(base_path)
        except ValueError as exc:
            raise ValueError(
                "Adopted files must share a common parent directory"
            ) from exc
    return base_path


def expand_adopt_paths(paths: Iterable[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        if resolved.is_dir():
            expanded.extend(
                sorted(child for child in resolved.rglob("*") if child.is_file())
            )
        else:
            expanded.append(resolved)
    if not expanded:
        raise ValueError("No files found to adopt")
    return expanded


def copy_adopted_files(
    paths: list[Path], module_dir: Path, base_path: Path
) -> list[Path]:
    module_paths: list[Path] = []
    for path in paths:
        relative = path.relative_to(base_path)
        destination = module_dir / relative
        destination = destination.with_name(to_module_filename(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        module_paths.append(destination)
    return module_paths


def adopt_files(
    paths: Iterable[Path],
    module_name: str,
    dotfiles_root: Path,
    render_root: Path,
    generation_repo: GenerationRepository,
    module_repo: DotfileModuleRepository,
    rendered_file_repo: RenderedFileRepository,
    deploy: bool = True,
) -> tuple[UUID | None, Path]:
    resolved = expand_adopt_paths(paths)

    base_path = ensure_parent_dir(resolved)
    module_name = normalize_module_name(module_name)

    module_dir = dotfiles_root / module_name
    if module_dir.exists():
        raise ValueError(f"Module directory already exists: {module_dir}")
    module_dir.mkdir(parents=True)

    copy_adopted_files(resolved, module_dir, base_path)

    if not deploy:
        return None, module_dir

    generation = generation_repo.create()
    variables = {"dotfile_dir": dotfiles_root.absolute().as_posix()}
    render_dotfiles(
        module_dir,
        module_name,
        base_path,
        variables,
        render_root,
        generation.id,
        module_repo=module_repo,
        rendered_file_repo=rendered_file_repo,
    )

    return generation.id, module_dir

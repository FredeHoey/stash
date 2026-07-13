from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from pathlib import Path


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
        destination = (module_dir / relative).with_name(to_module_filename(path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        module_paths.append(destination)
    return module_paths


def adopt_files(
    paths: Iterable[Path],
    module_name: str,
    dotfiles_root: Path,
) -> tuple[Path, Path]:
    resolved = expand_adopt_paths(paths)
    target_path = common_path(resolved)
    module_dir = dotfiles_root / normalize_module_name(module_name)
    if module_dir.exists():
        raise ValueError(f"Module directory already exists: {module_dir}")

    module_dir.mkdir(parents=True)
    copy_adopted_files(resolved, module_dir, target_path)
    return module_dir, target_path

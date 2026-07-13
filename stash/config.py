from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    return config


def write_config(path: Path, config: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)


def module_target(module_name: str, module_config: dict[str, Any]) -> Path:
    if target := module_config.get("target"):
        return Path(target).expanduser()
    return Path.home() / ".config" / module_name


def template_variables(
    config: dict[str, Any],
    dotfiles: Path,
) -> dict[str, Any]:
    variables = {"dotfile_dir": dotfiles.absolute().as_posix()}
    config_variables = config.get("variables", {})
    if not isinstance(config_variables, dict):
        raise ValueError("Config 'variables' must be a mapping")
    variables.update(config_variables)
    return variables


def ensure_dotfiles_module(config: dict[str, Any], module_name: str) -> dict[str, Any]:
    dotfiles = config.setdefault("dotfiles", {})
    if module_name not in dotfiles:
        dotfiles[module_name] = {}
    return config

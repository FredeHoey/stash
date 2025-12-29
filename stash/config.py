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


def ensure_dotfiles_module(config: dict[str, Any], module_name: str) -> dict[str, Any]:
    dotfiles = config.setdefault("dotfiles", {})
    if module_name not in dotfiles:
        dotfiles[module_name] = {}
    return config

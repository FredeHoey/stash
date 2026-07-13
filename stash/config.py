from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


BASE16_COLOR_NAMES = frozenset(f"base{index:02X}" for index in range(16))


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
    theme_name: str | None = None,
) -> dict[str, Any]:
    variables = {"dotfile_dir": dotfiles.absolute().as_posix()}
    config_variables = config.get("variables", {})
    if not isinstance(config_variables, dict):
        raise ValueError("Config 'variables' must be a mapping")
    if "colors" in config or "colors" in config_variables:
        raise ValueError(
            "The 'colors' mapping has been replaced by 'theme' and 'themes'"
        )
    variables.update(config_variables)

    selected_theme = resolve_theme(config, theme_name)
    if selected_theme is not None:
        selected_name, colors = selected_theme
        variables["theme"] = selected_name
        variables["colors"] = colors
    return variables


def resolve_theme(
    config: dict[str, Any],
    theme_name: str | None = None,
) -> tuple[str, dict[str, str]] | None:
    themes = config.get("themes")
    configured_name = config.get("theme")
    if themes is None:
        if configured_name is not None or theme_name is not None:
            raise ValueError("Config defines a theme but has no 'themes' mapping")
        return None
    if not isinstance(themes, dict) or not themes:
        raise ValueError("Config 'themes' must be a non-empty mapping")

    selected_name = theme_name if theme_name is not None else configured_name
    if not isinstance(selected_name, str) or not selected_name:
        raise ValueError("Config 'theme' must name the initial theme")
    colors = themes.get(selected_name)
    if not isinstance(colors, dict):
        raise ValueError(f"Unknown theme: {selected_name}")

    color_names = set(colors)
    if color_names != BASE16_COLOR_NAMES:
        missing = ", ".join(sorted(BASE16_COLOR_NAMES - color_names))
        extra = ", ".join(sorted(color_names - BASE16_COLOR_NAMES))
        details = []
        if missing:
            details.append(f"missing: {missing}")
        if extra:
            details.append(f"unexpected: {extra}")
        raise ValueError(
            f"Theme '{selected_name}' must define base00 through base0F "
            f"({'; '.join(details)})"
        )
    if not all(isinstance(value, str) for value in colors.values()):
        raise ValueError(f"Theme '{selected_name}' colors must be strings")
    return selected_name, dict(colors)


def ensure_dotfiles_module(config: dict[str, Any], module_name: str) -> dict[str, Any]:
    dotfiles = config.setdefault("dotfiles", {})
    if module_name not in dotfiles:
        dotfiles[module_name] = {}
    return config

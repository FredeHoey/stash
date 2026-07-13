from pathlib import Path

import pytest

from stash.config import BASE16_COLOR_NAMES, template_variables, theme_names
from stash.live import render_live


def _colors(prefix: str) -> dict[str, str]:
    return {name: f"{prefix}-{name}" for name in BASE16_COLOR_NAMES}


def _config() -> dict:
    return {
        "theme": "dark",
        "themes": {
            "dark": _colors("dark"),
            "light": _colors("light"),
        },
        "dotfiles": {},
    }


def test_template_variables_expose_selected_theme_as_colors(tmp_path: Path):
    config = _config()

    default_variables = template_variables(config, tmp_path)
    light_variables = template_variables(config, tmp_path, "light")

    assert default_variables["theme"] == "dark"
    assert default_variables["colors"]["base01"] == "dark-base01"
    assert light_variables["theme"] == "light"
    assert light_variables["colors"]["base01"] == "light-base01"


def test_theme_names_are_sorted():
    assert theme_names(_config()) == ["dark", "light"]
    assert theme_names({}) == []


def test_old_colors_mapping_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="replaced by 'theme' and 'themes'"):
        template_variables(
            {"variables": {"colors": _colors("old")}},
            tmp_path,
        )


def test_theme_requires_all_base16_colors(tmp_path: Path):
    config = _config()
    del config["themes"]["dark"]["base0F"]

    with pytest.raises(ValueError, match="missing: base0F"):
        template_variables(config, tmp_path)


def test_live_render_can_switch_theme_without_a_generation(tmp_path: Path):
    dotfiles = tmp_path / "dotfiles"
    module = dotfiles / "terminal"
    module.mkdir(parents=True)
    (module / "colors.conf").write_text("{{ colors.base01 }}")
    target = tmp_path / "target"
    live_root = tmp_path / "live"
    config = _config()
    config["dotfiles"] = {"terminal": {"target": target.as_posix()}}

    state = render_live(config, dotfiles, live_root)
    assert (live_root / "terminal" / "colors.conf").read_text() == "dark-base01"

    render_live(config, dotfiles, live_root, state, theme_name="light")
    assert (live_root / "terminal" / "colors.conf").read_text() == "light-base01"

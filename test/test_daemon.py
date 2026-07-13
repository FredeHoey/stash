from pathlib import Path

from stash.daemon import _is_relevant
from stash.live import render_live


def test_daemon_ignores_template_read_events(tmp_path: Path):
    module = tmp_path / "dotfiles" / "shell"
    module.mkdir(parents=True)
    template = module / "profile"
    config_path = tmp_path / "dotfiles" / "config.yaml"

    access_event = (None, ["IN_OPEN"], module.as_posix(), template.name)
    write_event = (None, ["IN_CLOSE_WRITE"], module.as_posix(), template.name)

    assert not _is_relevant([access_event], config_path, [module])
    assert _is_relevant([write_event], config_path, [module])


def test_render_live_updates_links_without_generations(tmp_path: Path):
    dotfiles = tmp_path / "dotfiles"
    module = dotfiles / "shell"
    module.mkdir(parents=True)
    template = module / "dot_profile"
    template.write_text("{{ value }}")
    target = tmp_path / "target"
    live_root = tmp_path / "live"
    config = {
        "variables": {"value": "first"},
        "dotfiles": {"shell": {"target": target.as_posix()}},
    }

    state = render_live(config, dotfiles, live_root)

    live_file = live_root / "shell" / ".profile"
    deployed_file = target / ".profile"
    assert live_file.read_text() == "first"
    assert deployed_file.resolve() == live_file.resolve()

    template.unlink()
    replacement = module / "settings.ini"
    replacement.write_text("{{ value }}")
    config["variables"]["value"] = "second"
    state = render_live(config, dotfiles, live_root, state)

    assert not deployed_file.exists()
    assert (target / "settings.ini").resolve() == (
        live_root / "shell" / "settings.ini"
    ).resolve()
    assert (live_root / "shell" / "settings.ini").read_text() == "second"

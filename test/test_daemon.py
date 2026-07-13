from pathlib import Path

from stash.daemon import _is_relevant
from stash.db import get_session
from stash.live import render_live, restore_latest
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)


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


def test_restore_latest_repoints_live_links(tmp_path: Path):
    db_path = tmp_path / "stash.sqlite"
    live_root = tmp_path / "live"
    dotfiles = tmp_path / "dotfiles"
    module_source = dotfiles / "shell"
    module_source.mkdir(parents=True)
    (module_source / "file.txt").write_text("live")
    target = tmp_path / "target"
    rendered_root = tmp_path / "rendered" / "shell"
    rendered_root.mkdir(parents=True)
    rendered_file = rendered_root / "file.txt"
    rendered_file.write_text("generated")

    with get_session(db_path) as session:
        generation = GenerationRepository(session).create()
        module = DotfileModuleRepository(session).create(
            generation_id=generation.id,
            module_name="shell",
            output_path=rendered_root,
            target_path=target,
        )
        RenderedFileRepository(session).create(
            module_id=module.id,
            file_path=rendered_file.as_posix(),
            template_path=(module_source / "file.txt").as_posix(),
            content_hash="hash",
        )

    state = render_live(
        {"dotfiles": {"shell": {"target": target.as_posix()}}},
        dotfiles,
        live_root,
    )
    assert (target / "file.txt").resolve() == live_root / "shell" / "file.txt"

    restore_latest(state, live_root, db_path)

    assert (target / "file.txt").resolve() == rendered_file.resolve()

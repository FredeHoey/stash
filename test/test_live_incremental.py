from pathlib import Path

from stash.live import _write_live_file, render_live


def test_render_live_rerenders_only_templates_using_changed_variables(
    tmp_path: Path,
    monkeypatch,
):
    dotfiles = tmp_path / "dotfiles"
    module = dotfiles / "shell"
    module.mkdir(parents=True)
    (module / "dot_profile").write_text("{{ value }}")
    (module / "dot_aliases").write_text("static")
    target = tmp_path / "target"
    live_root = tmp_path / "live"
    config = {
        "variables": {"value": "first"},
        "dotfiles": {"shell": {"target": target.as_posix()}},
    }

    state = render_live(config, dotfiles, live_root)
    writes: list[Path] = []

    def write_live_file(path: Path, content: str) -> None:
        writes.append(path.relative_to(live_root))
        _write_live_file(path, content)

    monkeypatch.setattr("stash.live._write_live_file", write_live_file)
    config["variables"]["value"] = "second"
    render_live(
        config,
        dotfiles,
        live_root,
        state,
        changed_variables={"value"},
    )

    assert writes == [Path("shell/.profile")]
    assert (live_root / "shell" / ".profile").read_text() == "second"
    assert (live_root / "shell" / ".aliases").read_text() == "static"


def test_render_live_rerenders_only_changed_template(tmp_path: Path, monkeypatch):
    dotfiles = tmp_path / "dotfiles"
    module = dotfiles / "shell"
    module.mkdir(parents=True)
    profile = module / "dot_profile"
    aliases = module / "dot_aliases"
    profile.write_text("first")
    aliases.write_text("same")
    target = tmp_path / "target"
    live_root = tmp_path / "live"
    config = {"dotfiles": {"shell": {"target": target.as_posix()}}}

    state = render_live(config, dotfiles, live_root)
    writes: list[Path] = []

    def write_live_file(path: Path, content: str) -> None:
        writes.append(path.relative_to(live_root))
        _write_live_file(path, content)

    monkeypatch.setattr("stash.live._write_live_file", write_live_file)
    profile.write_text("second")
    render_live(
        config,
        dotfiles,
        live_root,
        state,
        changed_paths={profile.resolve()},
    )

    assert writes == [Path("shell/.profile")]
    assert (live_root / "shell" / ".profile").read_text() == "second"
    assert (live_root / "shell" / ".aliases").read_text() == "same"


def test_render_live_rerenders_templates_depending_on_changed_include(
    tmp_path: Path,
    monkeypatch,
):
    dotfiles = tmp_path / "dotfiles"
    module = dotfiles / "shell"
    module.mkdir(parents=True)
    shared = module / "shared.txt"
    profile = module / "dot_profile"
    shared.write_text("first")
    profile.write_text('{% include "shared.txt" %}')
    target = tmp_path / "target"
    live_root = tmp_path / "live"
    config = {"dotfiles": {"shell": {"target": target.as_posix()}}}

    state = render_live(config, dotfiles, live_root)
    writes: list[Path] = []

    def write_live_file(path: Path, content: str) -> None:
        writes.append(path.relative_to(live_root))
        _write_live_file(path, content)

    monkeypatch.setattr("stash.live._write_live_file", write_live_file)
    shared.write_text("second")
    render_live(
        config,
        dotfiles,
        live_root,
        state,
        changed_paths={shared.resolve()},
    )

    assert writes == [Path("shell/.profile"), Path("shell/shared.txt")]
    assert (live_root / "shell" / ".profile").read_text() == "second"
    assert (live_root / "shell" / "shared.txt").read_text() == "second"

import asyncio
from pathlib import Path

import pytest

from stash.config import BASE16_COLOR_NAMES
from stash.hooks import HookError, HookRunner, dbus_event_name, discover_hooks


def test_dbus_event_name_uses_kebab_case():
    assert dbus_event_name("SetTheme") == "set-theme"
    assert dbus_event_name("Reload") == "reload"
    assert dbus_event_name("HTTPStatus") == "http-status"


def test_discover_hooks_filters_and_sorts_drop_ins(tmp_path: Path):
    event_directory = tmp_path / "post-set-theme.d"
    event_directory.mkdir()
    for name in (
        "20-second.py",
        "10-first.sh",
        "first.sh",
        "30-ignored.txt",
    ):
        (event_directory / name).write_text("")

    hooks = discover_hooks(tmp_path, "post-set-theme")

    assert [hook.name for hook in hooks] == ["10-first.sh", "20-second.py"]


def test_hook_runner_renders_and_runs_shell_and_python_hooks(tmp_path: Path):
    dotfiles = tmp_path / "dotfiles"
    hooks = dotfiles / "custom-hooks" / "post-set-theme.d"
    hooks.mkdir(parents=True)
    config_path = dotfiles / "config.yaml"
    config_path.write_text(
        "hooks_dir: custom-hooks\nvariables:\n  color: blue\ndotfiles: {}\n"
    )
    (hooks / "10-shell.sh").write_text(
        "printf '%s\\n' \"shell:{{ color }}:{{ arguments.theme }}:"
        '$STASH_ARG_THEME" >> hook.log\n'
    )
    (hooks / "20-python.py").write_text(
        'from pathlib import Path\nPath("hook.log").open("a").write('
        '"python:{{ event }}\\n")\n'
    )

    asyncio.run(
        HookRunner(config_path, dotfiles).run("SetTheme", {"theme": "dark"}, "post")
    )

    assert (dotfiles / "hook.log").read_text().splitlines() == [
        "shell:blue:dark:dark",
        "python:post-set-theme",
    ]


def test_hook_runner_stops_on_failed_hook(tmp_path: Path):
    dotfiles = tmp_path / "dotfiles"
    hooks = dotfiles / "hooks" / "pre-reload.d"
    hooks.mkdir(parents=True)
    config_path = dotfiles / "config.yaml"
    config_path.write_text("dotfiles: {}\n")
    (hooks / "10-fail.sh").write_text("exit 7\n")

    with pytest.raises(HookError, match="exit code 7"):
        asyncio.run(HookRunner(config_path, dotfiles).run("Reload", {}, "pre"))


def test_hook_runner_terminates_timed_out_hook(tmp_path: Path, monkeypatch):
    dotfiles = tmp_path / "dotfiles"
    hooks = dotfiles / "hooks" / "pre-reload.d"
    hooks.mkdir(parents=True)
    config_path = dotfiles / "config.yaml"
    config_path.write_text("dotfiles: {}\n")
    (hooks / "10-slow.sh").write_text("sleep 10\n")
    monkeypatch.setattr("stash.hooks.HOOK_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(HookError, match="exceeded the 0.01 second timeout"):
        asyncio.run(HookRunner(config_path, dotfiles).run("Reload", {}, "pre"))


def test_hook_templates_receive_active_theme(tmp_path: Path):
    dotfiles = tmp_path / "dotfiles"
    hooks = dotfiles / "hooks" / "post-set-theme.d"
    hooks.mkdir(parents=True)
    config_path = dotfiles / "config.yaml"
    colors = "\n".join(
        f'      {name}: "light-{name}"' for name in sorted(BASE16_COLOR_NAMES)
    )
    config_path.write_text(
        f"theme: light\nthemes:\n  light:\n{colors}\ndotfiles: {{}}\n"
    )
    (hooks / "10-theme.sh").write_text(
        "printf '%s' '{{ theme }}:{{ colors.base01 }}' > selected-theme\n"
    )

    asyncio.run(
        HookRunner(config_path, dotfiles, lambda: "light").run(
            "SetTheme", {"name": "light"}, "post"
        )
    )

    assert (dotfiles / "selected-theme").read_text() == "light:light-base01"


def test_hooks_directory_cannot_escape_dotfiles(tmp_path: Path):
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    config_path = dotfiles / "config.yaml"
    config_path.write_text("hooks_dir: ../hooks\ndotfiles: {}\n")

    with pytest.raises(HookError, match="within the dotfiles"):
        asyncio.run(HookRunner(config_path, dotfiles).run("Reload", {}, "pre"))

import argparse

import pytest

from stash import main
from stash.dbus_service import get_dbus_commands


@pytest.mark.parametrize(
    ("argv", "expected_handler"),
    [
        (["adopt", "/tmp/example"], main.adopt_command),
        (["daemon"], main.daemon_command),
        (["systemd-install"], main.systemd_install_command),
        (["ping"], main.dbus_command),
        (["reload"], main.dbus_command),
        (["set-theme", "kanagawa"], main.dbus_command),
        (["stop"], main.dbus_command),
    ],
)
def test_parse_args_sets_command_handler(argv, expected_handler):
    args = main.parse_args(argv)

    assert args.func is expected_handler


def test_parse_args_requires_command():
    with pytest.raises(SystemExit, match="2"):
        main.parse_args([])


def test_dbus_commands_are_generated_from_decorated_methods():
    commands = {command.cli_name: command for command in get_dbus_commands()}

    assert set(commands) == {"ping", "reload", "set-theme", "stop"}
    assert commands["set-theme"].method_name == "SetTheme"
    assert commands["set-theme"].input_signature == "s"
    assert [argument.name for argument in commands["set-theme"].arguments] == ["name"]


def test_dbus_command_calls_client(monkeypatch, capsys):
    calls = []

    async def call(command, arguments):
        calls.append((command.method_name, arguments))
        return [True]

    monkeypatch.setattr(main, "call_dbus_command", call)
    args = main.parse_args(["set-theme", "kanagawa"])

    assert main.dbus_command(args) == 0
    assert calls == [("SetTheme", ["kanagawa"])]
    assert capsys.readouterr().out == "true\n"


def test_main_dispatches_and_exits(monkeypatch):
    dispatched_args = None

    def command(args):
        nonlocal dispatched_args
        dispatched_args = args
        return 7

    args = argparse.Namespace(func=command)
    monkeypatch.setattr(main, "parse_args", lambda: args)

    with pytest.raises(SystemExit, match="7") as exc_info:
        main.main()

    assert exc_info.value.code == 7
    assert dispatched_args is args

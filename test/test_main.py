import argparse

import pytest

from stash import main


@pytest.mark.parametrize(
    ("argv", "expected_handler"),
    [
        (["adopt", "/tmp/example"], main.adopt_command),
        (["daemon"], main.daemon_command),
        (["systemd-install"], main.systemd_install_command),
    ],
)
def test_parse_args_sets_command_handler(argv, expected_handler):
    args = main.parse_args(argv)

    assert args.func is expected_handler


def test_parse_args_requires_command():
    with pytest.raises(SystemExit, match="2"):
        main.parse_args([])


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

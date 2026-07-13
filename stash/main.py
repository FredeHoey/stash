import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import questionary

from stash.adopt import adopt_files, common_path, expand_adopt_paths
from stash.config import add_dotfiles_module, load_config, write_config
from stash.daemon import DaemonError, run_daemon
from stash.dbus_client import DBusClientError, call_dbus_command, format_dbus_result
from stash.dbus_service import DBusCommand, get_dbus_commands
from stash.systemd import SystemdInstallError, install_user_service


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dotfiles", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(required=True)

    adopt_parser = subparsers.add_parser(
        "adopt",
        help="Copy existing files into a module managed by the daemon",
    )
    adopt_parser.set_defaults(func=adopt_command)
    adopt_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="File paths to adopt",
    )

    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Watch templates and render live updates",
    )
    daemon_parser.set_defaults(func=daemon_command)
    systemd_install_parser = subparsers.add_parser(
        "systemd-install",
        help="Install and start the stash systemd user service",
    )
    systemd_install_parser.set_defaults(func=systemd_install_command)

    for command in get_dbus_commands():
        command_parser = subparsers.add_parser(
            command.cli_name,
            help=command.description,
        )
        command_parser.set_defaults(func=dbus_command, command_spec=command)
        for argument in command.arguments:
            command_parser.add_argument(
                argument.name,
                type=_cli_argument_type(argument.python_type),
            )

    return parser.parse_args(argv)


def _parse_bool(value: str) -> bool:
    normalized = value.lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected a boolean value, got: {value}")


def _cli_argument_type(python_type: type[Any]):
    if python_type is bool:
        return _parse_bool
    if python_type in {str, int, float}:
        return python_type
    return json.loads


def load_command_config(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    config_path = args.config or args.dotfiles / "config.yaml"
    try:
        config = load_config(config_path)
    except FileNotFoundError as exc:
        print("No config.yaml file found, exiting...")
        raise SystemExit(1) from exc
    return config_path, config


def daemon_command(args: argparse.Namespace) -> int:
    config_path, _ = load_command_config(args)
    try:
        asyncio.run(
            run_daemon(
                config_path.resolve(),
                args.dotfiles.resolve(),
                Path.home() / ".local/share/stash/live",
            )
        )
    except DaemonError as exc:
        print(str(exc))
        return 1
    return 0


def systemd_install_command(args: argparse.Namespace) -> int:
    config_path, _ = load_command_config(args)
    try:
        unit_path = install_user_service(
            config_path.resolve(),
            args.dotfiles.resolve(),
        )
    except SystemdInstallError as exc:
        print(f"Could not install systemd service: {exc}")
        return 1
    print(f"Installed and started {unit_path}")
    return 0


def adopt_command(args: argparse.Namespace) -> int:
    config_path, config = load_command_config(args)
    base_path = common_path(args.paths)
    default_name = base_path.name or "module"
    suggested_name = questionary.text("Module name:", default=default_name).ask()
    if suggested_name is None:
        return 0
    module_name = suggested_name.strip()

    plan_lines = [str(path) for path in expand_adopt_paths(args.paths)]
    print("Files to adopt:")
    for line in plan_lines:
        print(f"- {line}")

    confirmed = questionary.confirm(
        "This will copy files into the dotfiles module. Continue?",
        default=False,
    ).ask()
    if not confirmed:
        return 0

    config = add_dotfiles_module(config, module_name, base_path)
    module_dir, target_path = adopt_files(
        args.paths,
        module_name,
        args.dotfiles,
    )
    config["dotfiles"][module_name]["target"] = target_path.as_posix()
    write_config(config_path, config)
    print(f"Adopted {module_name}; the daemon will deploy changes")
    print(f"Module created at {module_dir}")
    return 0


def dbus_command(args: argparse.Namespace) -> int:
    command: DBusCommand = args.command_spec
    arguments = [getattr(args, argument.name) for argument in command.arguments]
    try:
        result = asyncio.run(call_dbus_command(command, arguments))
    except DBusClientError as exc:
        print(str(exc))
        return 1
    output = format_dbus_result(result)
    if output:
        print(output)
    return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

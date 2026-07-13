import argparse
import asyncio
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

import questionary

from stash.adopt import (
    adopt_files,
    common_path,
    expand_adopt_paths,
    normalize_module_name,
)
from stash.cleanup import clean_orphan_generations
from stash.config import (
    ensure_dotfiles_module,
    load_config,
    module_target,
    template_variables,
    write_config,
)
from stash.db import get_session
from stash.daemon import DaemonError, run_daemon
from stash.history import render_history_from_repo
from stash.render import render_dotfiles
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)
from stash.rollback import RollbackError, rollback_to_generation
from stash.status import collect_status, render_status, render_status_json
from stash.systemd import SystemdInstallError, install_user_service


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dotfiles", type=Path, default=Path.cwd())
    parser.set_defaults(func=render_command)

    subparsers = parser.add_subparsers()
    history_parser = subparsers.add_parser("history", help="Show generation history")
    history_parser.set_defaults(func=history_command)
    history_parser.add_argument(
        "--json",
        action="store_true",
        help="Show generation history as JSON",
    )
    history_parser.add_argument(
        "modules",
        nargs="*",
        help="Filter history to one or more modules",
    )

    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback to a previous generation"
    )
    rollback_parser.set_defaults(func=rollback_command)
    rollback_parser.add_argument(
        "generation",
        type=str,
        help="Generation id for rollback",
    )
    rollback_parser.add_argument(
        "--modules",
        nargs="*",
        help="Module names for rollback",
    )
    rollback_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use interactive rollback prompts",
    )

    clean_parser = subparsers.add_parser(
        "clean",
        help="Remove generations with no modules",
    )
    clean_parser.set_defaults(func=clean_command)

    adopt_parser = subparsers.add_parser(
        "adopt",
        help="Adopt existing files into a new module",
    )
    adopt_parser.set_defaults(func=adopt_command)
    adopt_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="File paths to adopt",
    )
    adopt_parser.add_argument(
        "--deploy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Deploy symlinks after adopting",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Show rendered file status",
    )
    status_parser.set_defaults(func=status_command)
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Show status as JSON",
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

    return parser.parse_args(argv)


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


def history_command(args: argparse.Namespace) -> int:
    load_command_config(args)
    with get_session() as session:
        render_history_from_repo(
            GenerationRepository(session),
            DotfileModuleRepository(session),
            as_json=args.json,
            modules=set(args.modules),
        )
    return 0


def rollback_command(args: argparse.Namespace) -> int:
    load_command_config(args)
    try:
        generation_id = UUID(args.generation)
    except ValueError as exc:
        raise ValueError("Invalid generation id") from exc

    with get_session() as session:
        try:
            updated = rollback_to_generation(
                generation_id,
                DotfileModuleRepository(session),
                modules=args.modules,
            )
        except RollbackError as exc:
            print(str(exc))
            return 0

        for name, path in updated.items():
            print(f"Rolled back {name} -> {path}")
    return 0


def clean_command(args: argparse.Namespace) -> int:
    load_command_config(args)
    with get_session() as session:
        generation_repo = GenerationRepository(session)
        deleted = clean_orphan_generations(
            generation_repo,
            DotfileModuleRepository(session),
            Path.home() / ".local/share/stash/rendered",
        )
        if deleted:
            deleted_list = ", ".join(str(value) for value in deleted)
            print(f"Removed generations: {deleted_list}")
    return 0


def adopt_command(args: argparse.Namespace) -> int:
    config_path, config = load_command_config(args)
    with get_session() as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)

        base_path = common_path(args.paths)
        default_name = base_path.name or "module"
        suggested_name = questionary.text("Module name:", default=default_name).ask()
        if suggested_name is None:
            return 0
        module_name = normalize_module_name(suggested_name)

        plan_lines = [str(path) for path in expand_adopt_paths(args.paths)]
        print("Files to adopt:")
        for line in plan_lines:
            print(f"- {line}")

        confirm_copy = questionary.confirm(
            "This will copy files into the dotfiles module. Continue?",
            default=False,
        ).ask()
        if not confirm_copy:
            return 0

        if args.deploy:
            confirm_deploy = questionary.confirm(
                "Original files will be replaced by symlinks. Continue?",
                default=False,
            ).ask()
            if not confirm_deploy:
                return 0

        generation_id, module_dir = adopt_files(
            args.paths,
            module_name,
            args.dotfiles,
            Path.home() / ".local/share/stash/rendered",
            generation_repo,
            module_repo,
            rendered_file_repo,
            deploy=args.deploy,
        )
        config = ensure_dotfiles_module(config, module_name)
        write_config(config_path, config)
        if generation_id is not None:
            print(f"Adopted {module_name} as generation {generation_id}")
        else:
            print(f"Adopted {module_name} (no deployment)")
        print(f"Module created at {module_dir}")
    return 0


def status_command(args: argparse.Namespace) -> int:
    load_command_config(args)
    with get_session() as session:
        statuses = collect_status(
            DotfileModuleRepository(session),
            RenderedFileRepository(session),
        )
        if args.json:
            render_status_json(statuses)
        else:
            render_status(statuses)
    return 0


def render_command(args: argparse.Namespace) -> int:
    config_path, config = load_command_config(args)

    config_hash = sha256(config_path.read_bytes()).hexdigest()

    with get_session() as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)

        generation = generation_repo.create()
        updated_modules: list[str] = []
        variables = template_variables(config, args.dotfiles)

        for module_name, module_config in config["dotfiles"].items():
            target_path = module_target(module_name, module_config)

            render_path = Path.home() / ".local/share/stash/rendered"

            updated = render_dotfiles(
                args.dotfiles / module_name,
                module_name,
                target_path,
                variables,
                render_path,
                generation.id,
                module_repo=module_repo,
                rendered_file_repo=rendered_file_repo,
                config_hash=config_hash,
            )
            if updated:
                updated_modules.append(module_name)

        if not updated_modules:
            generation_repo.delete(generation)
            print("No changes detected")
            return 0

        print(f"Generation {generation.id} complete")
    return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()

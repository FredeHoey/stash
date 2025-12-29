import argparse
from pathlib import Path
from uuid import UUID

import questionary

from stash.adopt import (
    adopt_files,
    common_path,
    expand_adopt_paths,
    normalize_module_name,
)
from stash.cleanup import clean_orphan_generations
from stash.config import ensure_dotfiles_module, load_config, write_config
from stash.db import get_session, init_db
from stash.history import render_history_from_repo
from stash.render import render_dotfiles
from stash.repositories import (
    DotfileModuleRepository,
    GenerationRepository,
    RenderedFileRepository,
)
from stash.rollback import RollbackError, rollback_to_generation
from stash.status import collect_status, render_status, render_status_json


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dotfiles", type=Path, default=Path.cwd())

    subparsers = parser.add_subparsers(dest="command")
    history_parser = subparsers.add_parser("history", help="Show generation history")
    history_parser.add_argument(
        "--json",
        action="store_true",
        help="Show generation history as JSON",
    )
    history_parser.add_argument(
        "--module",
        type=str,
        help="Filter history to a single module",
    )

    rollback_parser = subparsers.add_parser(
        "rollback", help="Rollback to a previous generation"
    )
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

    subparsers.add_parser(
        "clean",
        help="Remove generations with no modules",
    )

    adopt_parser = subparsers.add_parser(
        "adopt",
        help="Adopt existing files into a new module",
    )
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
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Show status as JSON",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    config_path = args.config or args.dotfiles / "config.yaml"
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        print("No config.yaml file found, exiting...")
        exit(1)

    init_db()

    with get_session() as session:
        generation_repo = GenerationRepository(session)
        module_repo = DotfileModuleRepository(session)
        rendered_file_repo = RenderedFileRepository(session)

        if args.command == "history":
            render_history_from_repo(
                generation_repo,
                module_repo,
                as_json=args.json,
                module=args.module,
            )
            return

        if args.command == "rollback":
            try:
                generation_id = UUID(args.generation)
            except ValueError as exc:
                raise ValueError("Invalid generation id") from exc

            try:
                updated = rollback_to_generation(
                    generation_id,
                    module_repo,
                    modules=args.modules,
                )
            except RollbackError as exc:
                print(str(exc))
                return

            for name, path in updated.items():
                print(f"Rolled back {name} -> {path}")
            return

        if args.command == "clean":
            deleted = clean_orphan_generations(
                generation_repo,
                module_repo,
                Path.home() / ".local/share/stash/rendered",
            )
            if deleted:
                deleted_list = ", ".join(str(value) for value in deleted)
                print(f"Removed generations: {deleted_list}")
            return

        if args.command == "adopt":
            base_path = common_path(args.paths)
            default_name = base_path.name or "module"
            suggested_name = questionary.text(
                "Module name:", default=default_name
            ).ask()
            if suggested_name is None:
                return
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
                return

            if args.deploy:
                confirm_deploy = questionary.confirm(
                    "Original files will be replaced by symlinks. Continue?",
                    default=False,
                ).ask()
                if not confirm_deploy:
                    return

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
            return

        if args.command == "status":
            statuses = collect_status(module_repo, rendered_file_repo)
            if args.json:
                render_status_json(statuses)
            else:
                render_status(statuses)
            return

        generation = generation_repo.create()
        updated_modules: list[str] = []

        for module_name, module_config in config["dotfiles"].items():
            if target := module_config.get("target"):
                target_path = Path(target).expanduser()
            else:
                target_path = Path.home() / ".config" / module_name

            render_path = Path.home() / ".local/share/stash/rendered"

            variables = {"dotfile_dir": args.dotfiles.absolute().as_posix()}
            if config_vars := config.get("variables"):
                variables.update(config_vars)

            updated = render_dotfiles(
                args.dotfiles / module_name,
                module_name,
                target_path,
                variables,
                render_path,
                generation.id,
                module_repo=module_repo,
                rendered_file_repo=rendered_file_repo,
            )
            if updated:
                updated_modules.append(module_name)

        if not updated_modules:
            generation_repo.delete(generation)
            print("No changes detected")
            return

        print(f"Generation {generation.id} complete")


if __name__ == "__main__":
    main()

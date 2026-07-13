from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import signal
import sys
from typing import Any, Callable

from jinja2 import TemplateError

from stash.config import load_config, template_variables
from stash.templates import template_environment


_HOOK_PATTERN = re.compile(r"^[0-9]{2}-.+\.(?:py|sh)$")
_DBUS_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
HOOK_TIMEOUT_SECONDS = 1.0


class HookError(RuntimeError):
    pass


def dbus_event_name(method_name: str) -> str:
    return _DBUS_WORD_BOUNDARY.sub("-", method_name).lower()


def hooks_root(config: dict[str, Any], dotfiles: Path) -> Path:
    configured = config.get("hooks_dir", "hooks")
    if not isinstance(configured, str):
        raise HookError("Config 'hooks_dir' must be a relative path")
    relative_path = Path(configured)
    if relative_path.is_absolute():
        raise HookError("Config 'hooks_dir' must be relative to the dotfiles directory")
    root = (dotfiles / relative_path).resolve()
    if not root.is_relative_to(dotfiles.resolve()):
        raise HookError("Config 'hooks_dir' must stay within the dotfiles directory")
    return root


def discover_hooks(root: Path, event: str) -> list[Path]:
    event_directory = (root / f"{event}.d").resolve()
    if not event_directory.is_relative_to(root.resolve()):
        raise HookError(f"Hook event directory escapes the hooks directory: {event}")
    if not event_directory.is_dir():
        return []
    return sorted(
        path
        for path in event_directory.iterdir()
        if path.is_file()
        and path.resolve().is_relative_to(root.resolve())
        and _HOOK_PATTERN.fullmatch(path.name)
    )


def _hook_environment(event: str, arguments: dict[str, Any]) -> dict[str, str]:
    environment = os.environ.copy()
    environment["STASH_EVENT"] = event
    environment["STASH_ARGUMENTS"] = json.dumps(arguments, sort_keys=True)
    for name, value in arguments.items():
        environment_name = re.sub(r"[^A-Z0-9]", "_", name.upper())
        environment[f"STASH_ARG_{environment_name}"] = (
            value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        )
    return environment


async def _run_script(
    script_path: Path,
    content: str,
    dotfiles: Path,
    event: str,
    arguments: dict[str, Any],
) -> None:
    interpreter = sys.executable if script_path.suffix == ".py" else "/bin/sh"
    process: asyncio.subprocess.Process | None = None
    try:
        async with asyncio.timeout(HOOK_TIMEOUT_SECONDS):
            process = await asyncio.create_subprocess_exec(
                interpreter,
                "-",
                cwd=dotfiles,
                env=_hook_environment(event, arguments),
                stdin=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            await process.communicate(content.encode())
    except TimeoutError as exc:
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        raise HookError(
            f"Hook {script_path} exceeded the {HOOK_TIMEOUT_SECONDS:g} second timeout"
        ) from exc
    if process is None:
        raise HookError(f"Could not start hook {script_path}")
    if process.returncode != 0:
        raise HookError(
            f"Hook {script_path} failed with exit code {process.returncode}"
        )


class HookRunner:
    def __init__(
        self,
        config_path: Path,
        dotfiles: Path,
        active_theme: Callable[[], str | None] | None = None,
    ) -> None:
        self._config_path = config_path
        self._dotfiles = dotfiles
        self._active_theme = active_theme or (lambda: None)

    async def run(
        self,
        method_name: str,
        arguments: dict[str, Any],
        phase: str,
    ) -> None:
        if phase not in {"pre", "post"}:
            raise HookError(f"Unknown hook phase: {phase}")
        event = f"{phase}-{dbus_event_name(method_name)}"
        config = load_config(self._config_path)
        root = hooks_root(config, self._dotfiles)
        scripts = discover_hooks(root, event)
        if not scripts:
            return

        variables = template_variables(
            config,
            self._dotfiles,
            self._active_theme(),
        )
        variables.update({"event": event, "arguments": arguments})
        environment = template_environment(root)
        for script_path in scripts:
            template_name = script_path.relative_to(root).as_posix()
            try:
                content = environment.get_template(template_name).render(variables)
            except (TemplateError, UnicodeDecodeError) as exc:
                raise HookError(f"Could not render hook {script_path}: {exc}") from exc
            await _run_script(
                script_path,
                content,
                self._dotfiles,
                event,
                arguments,
            )

from __future__ import annotations

import asyncio
from collections.abc import Iterable
import fcntl
from pathlib import Path
import signal
from typing import Any, TextIO

from inotify.adapters import InotifyTree
from inotify.constants import (
    IN_CLOSE_WRITE,
    IN_CREATE,
    IN_DELETE,
    IN_DELETE_SELF,
    IN_MODIFY,
    IN_MOVED_FROM,
    IN_MOVED_TO,
    IN_MOVE_SELF,
)
import yaml

from stash.config import load_config, resolve_theme, theme_names
from stash.dbus_service import DBusServiceError, start_dbus_service
from stash.hooks import HookRunner
from stash.live import DaemonError, LiveState, render_live


_MUTATION_EVENT_NAMES = frozenset(
    {
        "IN_CLOSE_WRITE",
        "IN_CREATE",
        "IN_DELETE",
        "IN_DELETE_SELF",
        "IN_MODIFY",
        "IN_MOVED_FROM",
        "IN_MOVED_TO",
        "IN_MOVE_SELF",
    }
)
_WATCH_MASK = (
    IN_CLOSE_WRITE
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MODIFY
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_MOVE_SELF
)


def _poll_events(watcher: InotifyTree) -> list[tuple[Any, ...]]:
    events: list[tuple[Any, ...]] = []
    for event in watcher.event_gen(timeout_s=0.25, yield_nones=False):
        if event is not None:
            events.append(event)
    return events


def _is_relevant(
    events: Iterable[tuple[Any, ...]],
    config_path: Path,
    source_paths: Iterable[Path],
) -> bool:
    for _, event_names, watched_path, filename in events:
        if _MUTATION_EVENT_NAMES.isdisjoint(event_names):
            continue
        changed_path = (Path(watched_path) / filename).resolve(strict=False)
        if changed_path == config_path.resolve():
            return True
        for source in source_paths:
            if changed_path == source:
                return True
            if changed_path.is_relative_to(source):
                relative_path = changed_path.relative_to(source)
                if not relative_path.parts or relative_path.parts[0] != ".git":
                    return True
    return False


def _acquire_lock(live_root: Path) -> TextIO:
    live_root.mkdir(parents=True, exist_ok=True)
    lock_file = (live_root / ".daemon.lock").open("w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise DaemonError("Another stash daemon is already running") from exc
    return lock_file


def _with_configured_sources(
    state: LiveState,
    config: dict[str, Any],
    dotfiles: Path,
) -> LiveState:
    modules = config.get("dotfiles", {})
    source_paths = set(state.source_paths)
    if isinstance(modules, dict):
        source_paths.update(
            (dotfiles / name).resolve() for name in modules if isinstance(name, str)
        )
    return LiveState(
        active_links=state.active_links,
        module_names=state.module_names,
        source_paths=frozenset(source_paths),
    )


async def run_daemon(config_path: Path, dotfiles: Path, live_root: Path) -> None:
    lock_file = _acquire_lock(live_root)
    state: LiveState | None = None
    bus = None
    stop_event = asyncio.Event()
    active_theme: str | None = None
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
            installed_signals.append(signal_name)
        except NotImplementedError:
            pass

    try:
        watchers = [InotifyTree(dotfiles.as_posix(), mask=_WATCH_MASK)]
        if not config_path.resolve().is_relative_to(dotfiles.resolve()):
            watchers.append(
                InotifyTree(config_path.parent.as_posix(), mask=_WATCH_MASK)
            )

        initial_config = load_config(config_path)
        initial_theme = resolve_theme(initial_config)
        active_theme = initial_theme[0] if initial_theme is not None else None
        state = render_live(
            initial_config,
            dotfiles,
            live_root,
            theme_name=active_theme,
        )

        def apply_config(
            config: dict[str, Any],
            requested_theme: str | None,
            fallback_if_missing: bool = False,
        ) -> None:
            nonlocal active_theme, state
            themes = config.get("themes")
            if (
                fallback_if_missing
                and requested_theme is not None
                and isinstance(themes, dict)
                and requested_theme not in themes
            ):
                requested_theme = None
            selected_theme = resolve_theme(config, requested_theme)
            selected_name = selected_theme[0] if selected_theme is not None else None
            state = render_live(
                config,
                dotfiles,
                live_root,
                state,
                theme_name=selected_name,
            )
            active_theme = selected_name

        async def reload_handler() -> bool:
            apply_config(
                load_config(config_path),
                active_theme,
                fallback_if_missing=True,
            )
            print("Live configuration updated")
            return True

        async def set_theme_handler(name: str) -> bool:
            apply_config(load_config(config_path), name)
            print(f"Theme changed to {name}")
            return True

        async def list_themes_handler() -> list[str]:
            return theme_names(load_config(config_path))

        try:
            bus = await start_dbus_service(
                reload_handler,
                set_theme_handler,
                list_themes_handler,
                stop_event,
                HookRunner(config_path, dotfiles, lambda: active_theme),
            )
        except DBusServiceError as exc:
            raise DaemonError(str(exc)) from exc
        print(f"Watching {dotfiles} for changes; D-Bus name: org.dotstash.Stash")
        while not stop_event.is_set():
            changed = False
            for watcher in watchers:
                events = await asyncio.to_thread(_poll_events, watcher)
                if _is_relevant(events, config_path, state.source_paths):
                    changed = True
            if stop_event.is_set():
                break
            if not changed:
                continue
            await asyncio.sleep(0.1)
            candidate_config: dict[str, Any] | None = None
            try:
                candidate_config = load_config(config_path)
                apply_config(
                    candidate_config,
                    active_theme,
                    fallback_if_missing=True,
                )
                print("Live configuration updated")
            except (DaemonError, OSError, yaml.YAMLError) as exc:
                if candidate_config is not None:
                    state = _with_configured_sources(
                        state,
                        candidate_config,
                        dotfiles,
                    )
                print(f"Live update failed: {exc}")
    finally:
        if bus is not None:
            bus.disconnect()
        for signal_name in installed_signals:
            loop.remove_signal_handler(signal_name)
        lock_file.close()

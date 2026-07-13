from __future__ import annotations

import asyncio
from functools import wraps
import inspect
from typing import Any, Awaitable, Callable

from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.annotations import DBusBool, DBusStr
from dbus_fast.constants import RequestNameReply
from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, dbus_method

from stash.hooks import HookRunner


BUS_NAME = "org.dotstash.Stash"
INTERFACE_NAME = "org.dotstash.Stash1"
OBJECT_PATH = "/org/dotstash/Stash"


class DBusServiceError(RuntimeError):
    pass


def stash_dbus_method():
    def decorate(
        function: Callable[..., Awaitable[Any]],
    ) -> Callable[..., None]:
        signature = inspect.signature(function)
        method_name = getattr(function, "__name__", function.__class__.__name__)

        @wraps(function)
        async def run_with_hooks(interface, *args, **kwargs):
            bound = signature.bind(interface, *args, **kwargs)
            arguments = dict(bound.arguments)
            arguments.pop("self", None)
            try:
                await interface._hook_runner.run(method_name, arguments, "pre")
            except Exception as exc:
                raise DBusError(f"{INTERFACE_NAME}.PreHookError", str(exc)) from exc
            try:
                result = await function(interface, *args, **kwargs)
            except Exception as exc:
                raise DBusError(f"{INTERFACE_NAME}.MethodError", str(exc)) from exc
            try:
                await interface._hook_runner.run(method_name, arguments, "post")
            except Exception as exc:
                raise DBusError(f"{INTERFACE_NAME}.PostHookError", str(exc)) from exc
            return result

        return dbus_method()(run_with_hooks)

    return decorate


class StashInterface(ServiceInterface):
    def __init__(
        self,
        reload_handler: Callable[[], Awaitable[bool]],
        set_theme_handler: Callable[[str], Awaitable[bool]],
        stop_event: asyncio.Event,
        hook_runner: HookRunner,
    ) -> None:
        super().__init__(INTERFACE_NAME)
        self._reload_handler = reload_handler
        self._set_theme_handler = set_theme_handler
        self._stop_event = stop_event
        self._hook_runner = hook_runner

    def ping(self) -> str:
        return "pong"

    def stop(self) -> bool:
        self._stop_event.set()
        return True

    @stash_dbus_method()
    async def Ping(self) -> DBusStr:
        return self.ping()

    @stash_dbus_method()
    async def Reload(self) -> DBusBool:
        return await self._reload_handler()

    @stash_dbus_method()
    async def SetTheme(self, name: DBusStr) -> DBusBool:
        return await self._set_theme_handler(name)

    @stash_dbus_method()
    async def Stop(self) -> DBusBool:
        return self.stop()


async def start_dbus_service(
    reload_handler: Callable[[], Awaitable[bool]],
    set_theme_handler: Callable[[str], Awaitable[bool]],
    stop_event: asyncio.Event,
    hook_runner: HookRunner,
) -> MessageBus:
    bus: MessageBus | None = None
    try:
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        bus.export(
            OBJECT_PATH,
            StashInterface(
                reload_handler,
                set_theme_handler,
                stop_event,
                hook_runner,
            ),
        )
        reply = await bus.request_name(BUS_NAME)
    except Exception as exc:
        if bus is not None:
            bus.disconnect()
        raise DBusServiceError(f"Could not start D-Bus service: {exc}") from exc

    if reply not in {
        RequestNameReply.PRIMARY_OWNER,
        RequestNameReply.ALREADY_OWNER,
    }:
        bus.disconnect()
        raise DBusServiceError(f"D-Bus name is already owned: {BUS_NAME}")
    return bus

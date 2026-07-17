from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import wraps
import inspect
from typing import (
    Annotated,
    Any,
    Awaitable,
    Callable,
    Protocol,
    get_args,
    get_origin,
    get_type_hints,
)

from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.annotations import DBusBool, DBusSignature, DBusStr
from dbus_fast.constants import RequestNameReply
from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, dbus_method

from stash.hooks import dbus_event_name


BUS_NAME = "org.dotstash.Stash"
INTERFACE_NAME = "org.dotstash.Stash1"
OBJECT_PATH = "/org/dotstash/Stash"
DBusStrList = Annotated[list[str], DBusSignature("as")]


class HookRunner(Protocol):
    async def run(
        self,
        method_name: str,
        arguments: dict[str, Any],
        phase: str,
    ) -> None: ...


class DBusServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class DBusCommandArgument:
    name: str
    signature: str
    python_type: type[Any]


@dataclass(frozen=True)
class DBusCommand:
    method_name: str
    cli_name: str
    description: str
    arguments: tuple[DBusCommandArgument, ...]

    @property
    def input_signature(self) -> str:
        return "".join(argument.signature for argument in self.arguments)


_COMMAND_ATTRIBUTE = "__stash_dbus_command__"


def _dbus_command_argument(
    parameter: inspect.Parameter,
    annotation: Any,
) -> DBusCommandArgument:
    if get_origin(annotation) is not Annotated:
        raise TypeError(f"D-Bus argument '{parameter.name}' must use DBus annotations")
    python_annotation, *metadata = get_args(annotation)
    dbus_signature = next(
        (item.signature for item in metadata if isinstance(item, DBusSignature)),
        None,
    )
    python_type = get_origin(python_annotation) or python_annotation
    if dbus_signature is None or not isinstance(python_type, type):
        raise TypeError(f"D-Bus argument '{parameter.name}' has an invalid annotation")
    return DBusCommandArgument(parameter.name, dbus_signature, python_type)


def stash_dbus_method(description: str | None = None):
    def decorate(
        function: Callable[..., Awaitable[Any]],
    ) -> Callable[..., None]:
        signature = inspect.signature(function)
        method_name = getattr(function, "__name__", function.__class__.__name__)
        type_hints = get_type_hints(function, include_extras=True)
        arguments = tuple(
            _dbus_command_argument(parameter, type_hints[parameter.name])
            for parameter in signature.parameters.values()
            if parameter.name != "self"
        )
        command = DBusCommand(
            method_name=method_name,
            cli_name=dbus_event_name(method_name),
            description=description or f"Call the daemon's {method_name} method",
            arguments=arguments,
        )

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

        method = dbus_method()(run_with_hooks)
        setattr(method, _COMMAND_ATTRIBUTE, command)
        return method

    return decorate


class StashInterface(ServiceInterface):
    def __init__(
        self,
        reload_handler: Callable[[], Awaitable[bool]],
        set_theme_handler: Callable[[str], Awaitable[bool]],
        stop_event: asyncio.Event,
        hook_runner: HookRunner,
        list_themes_handler: Callable[[], Awaitable[list[str]]] | None = None,
        get_theme_handler: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        super().__init__(INTERFACE_NAME)
        self._reload_handler = reload_handler
        self._set_theme_handler = set_theme_handler
        self._list_themes_handler = list_themes_handler or _empty_theme_list
        self._get_theme_handler = get_theme_handler or _empty_theme_name
        self._stop_event = stop_event
        self._hook_runner = hook_runner

    def ping(self) -> str:
        return "pong"

    def stop(self) -> bool:
        self._stop_event.set()
        return True

    @stash_dbus_method("Check whether the stash daemon is available")
    async def Ping(self) -> DBusStr:
        return self.ping()

    @stash_dbus_method("Reload the daemon configuration")
    async def Reload(self) -> DBusBool:
        return await self._reload_handler()

    @stash_dbus_method("Change the active theme")
    async def SetTheme(self, name: DBusStr) -> DBusBool:
        return await self._set_theme_handler(name)

    @stash_dbus_method("List the available themes")
    async def ListThemes(self) -> DBusStrList:
        return await self._list_themes_handler()

    @stash_dbus_method("Get the active theme")
    async def GetTheme(self) -> DBusStr:
        return await self._get_theme_handler()

    @stash_dbus_method("Stop the stash daemon")
    async def Stop(self) -> DBusBool:
        return self.stop()


async def start_dbus_service(
    reload_handler: Callable[[], Awaitable[bool]],
    set_theme_handler: Callable[[str], Awaitable[bool]],
    list_themes_handler: Callable[[], Awaitable[list[str]]],
    get_theme_handler: Callable[[], Awaitable[str]],
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
                list_themes_handler,
                get_theme_handler,
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


async def _empty_theme_list() -> list[str]:
    return []


async def _empty_theme_name() -> str:
    return ""


def get_dbus_commands() -> tuple[DBusCommand, ...]:
    commands: list[DBusCommand] = []
    for value in vars(StashInterface).values():
        command = getattr(value, _COMMAND_ATTRIBUTE, None)
        if isinstance(command, DBusCommand):
            commands.append(command)
    return tuple(commands)

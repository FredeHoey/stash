from __future__ import annotations

from typing import Any

from dbus_fast import BusType, Message
from dbus_fast.aio import MessageBus
from dbus_fast.constants import MessageType

from stash.dbus_service import BUS_NAME, INTERFACE_NAME, OBJECT_PATH, DBusCommand


class DBusClientError(RuntimeError):
    pass


async def call_dbus_command(
    command: DBusCommand,
    arguments: list[Any],
) -> list[Any]:
    bus: MessageBus | None = None
    try:
        connected_bus = await MessageBus(bus_type=BusType.SESSION).connect()
        bus = connected_bus
        reply = await connected_bus.call(
            Message(
                destination=BUS_NAME,
                path=OBJECT_PATH,
                interface=INTERFACE_NAME,
                member=command.method_name,
                signature=command.input_signature,
                body=arguments,
            )
        )
        if reply.message_type == MessageType.ERROR:
            detail = str(reply.body[0]) if reply.body else str(reply.error_name)
            raise DBusClientError(detail)
        return reply.body
    except DBusClientError:
        raise
    except Exception as exc:
        raise DBusClientError(f"Could not call stash daemon: {exc}") from exc
    finally:
        if bus is not None:
            bus.disconnect()


def format_dbus_result(values: list[Any]) -> str:
    def format_value(value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    if len(values) == 1 and isinstance(values[0], list):
        values = values[0]
    return "\n".join(format_value(value) for value in values)

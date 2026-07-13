import asyncio
from types import SimpleNamespace

from dbus_fast.constants import MessageType

from stash import dbus_client
from stash.dbus_service import BUS_NAME, INTERFACE_NAME, OBJECT_PATH, get_dbus_commands


def test_call_dbus_command_sends_registered_method(monkeypatch):
    sent_messages = []

    class FakeBus:
        async def connect(self):
            return self

        async def call(self, message):
            sent_messages.append(message)
            return SimpleNamespace(
                message_type=MessageType.METHOD_RETURN,
                body=[True],
            )

        def disconnect(self):
            pass

    monkeypatch.setattr(dbus_client, "MessageBus", lambda **kwargs: FakeBus())
    command = next(
        command for command in get_dbus_commands() if command.cli_name == "set-theme"
    )

    result = asyncio.run(dbus_client.call_dbus_command(command, ["kanagawa"]))

    assert result == [True]
    assert len(sent_messages) == 1
    message = sent_messages[0]
    assert message.destination == BUS_NAME
    assert message.path == OBJECT_PATH
    assert message.interface == INTERFACE_NAME
    assert message.member == "SetTheme"
    assert message.signature == "s"
    assert message.body == ["kanagawa"]


def test_call_dbus_command_surfaces_daemon_errors(monkeypatch):
    class FakeBus:
        async def connect(self):
            return self

        async def call(self, message):
            return SimpleNamespace(
                message_type=MessageType.ERROR,
                error_name=f"{INTERFACE_NAME}.MethodError",
                body=["unknown theme"],
            )

        def disconnect(self):
            pass

    monkeypatch.setattr(dbus_client, "MessageBus", lambda **kwargs: FakeBus())
    command = next(
        command for command in get_dbus_commands() if command.cli_name == "set-theme"
    )

    try:
        asyncio.run(dbus_client.call_dbus_command(command, ["missing"]))
    except dbus_client.DBusClientError as exc:
        assert str(exc) == "unknown theme"
    else:
        raise AssertionError("Expected the D-Bus error to reach the client")

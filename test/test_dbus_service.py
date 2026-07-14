import asyncio

from dbus_fast.annotations import DBusBool, DBusStr
from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface
import pytest

from stash.dbus_service import INTERFACE_NAME, StashInterface, stash_dbus_method


class FakeHookRunner:
    def __init__(self):
        self.calls: list[tuple[str, dict, str]] = []

    async def run(self, method_name: str, arguments: dict, phase: str) -> None:
        self.calls.append((method_name, arguments, phase))


def test_dbus_interface_exposes_daemon_commands():
    stop_event = asyncio.Event()

    async def reload_handler():
        return True

    async def set_theme_handler(name: str):
        return bool(name)

    interface = StashInterface(
        reload_handler,
        set_theme_handler,
        stop_event,
        FakeHookRunner(),
    )

    assert interface.name == INTERFACE_NAME
    assert interface.ping() == "pong"
    assert interface.stop() is True
    assert stop_event.is_set()


def test_dbus_method_runs_matching_hook():
    async def run():
        hook_runner = FakeHookRunner()

        async def reload_handler():
            return True

        async def set_theme_handler(name: str):
            return bool(name)

        interface = StashInterface(
            reload_handler,
            set_theme_handler,
            asyncio.Event(),
            hook_runner,
        )

        result = await getattr(interface.Reload, "__wrapped__")(interface)

        assert result is True
        assert hook_runner.calls == [
            ("Reload", {}, "pre"),
            ("Reload", {}, "post"),
        ]

    asyncio.run(run())


def test_set_theme_runs_action_before_hook_with_named_argument():
    async def run():
        order: list[str] = []

        class OrderedHookRunner(FakeHookRunner):
            async def run(self, method_name: str, arguments: dict, phase: str) -> None:
                order.append(f"{phase}-hook")
                await super().run(method_name, arguments, phase)

        async def reload_handler():
            return True

        async def set_theme_handler(name: str):
            order.append(f"theme:{name}")
            return True

        hook_runner = OrderedHookRunner()
        interface = StashInterface(
            reload_handler,
            set_theme_handler,
            asyncio.Event(),
            hook_runner,
        )

        result = await getattr(interface.SetTheme, "__wrapped__")(interface, "dark")

        assert result is True
        assert order == ["pre-hook", "theme:dark", "post-hook"]
        assert hook_runner.calls == [
            ("SetTheme", {"name": "dark"}, "pre"),
            ("SetTheme", {"name": "dark"}, "post"),
        ]

    asyncio.run(run())


def test_list_themes_returns_available_names():
    async def run():
        async def reload_handler():
            return True

        async def set_theme_handler(name: str):
            return bool(name)

        async def list_themes_handler():
            return ["kanagawa", "solarized"]

        interface = StashInterface(
            reload_handler,
            set_theme_handler,
            asyncio.Event(),
            FakeHookRunner(),
            list_themes_handler,
        )

        result = await getattr(interface.ListThemes, "__wrapped__")(interface)

        assert result == ["kanagawa", "solarized"]

    asyncio.run(run())


@pytest.mark.parametrize(
    ("failed_phase", "action_runs"),
    [("pre", False), ("post", True)],
)
def test_hook_failure_respects_lifecycle_phase(failed_phase: str, action_runs: bool):
    async def run():
        actions: list[str] = []

        class FailingHookRunner(FakeHookRunner):
            async def run(self, method_name: str, arguments: dict, phase: str) -> None:
                if phase == failed_phase:
                    raise RuntimeError(f"{phase} failed")
                await super().run(method_name, arguments, phase)

        async def reload_handler():
            actions.append("reload")
            return True

        async def set_theme_handler(name: str):
            return bool(name)

        interface = StashInterface(
            reload_handler,
            set_theme_handler,
            asyncio.Event(),
            FailingHookRunner(),
        )

        with pytest.raises(DBusError, match=f"{failed_phase} failed"):
            await getattr(interface.Reload, "__wrapped__")(interface)

        assert bool(actions) is action_runs

    asyncio.run(run())


def test_dbus_method_passes_named_arguments_to_hook():
    class ThemeInterface(ServiceInterface):
        def __init__(self, hook_runner):
            super().__init__("org.dotstash.Test1")
            self._hook_runner = hook_runner

        @stash_dbus_method()
        async def SetTheme(self, theme: DBusStr) -> DBusBool:
            return bool(theme)

    async def run():
        hook_runner = FakeHookRunner()
        interface = ThemeInterface(hook_runner)

        result = await getattr(interface.SetTheme, "__wrapped__")(interface, "dark")

        assert result is True
        assert hook_runner.calls == [
            ("SetTheme", {"theme": "dark"}, "pre"),
            ("SetTheme", {"theme": "dark"}, "post"),
        ]

    asyncio.run(run())

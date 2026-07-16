from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import echobot.channels.platforms.telegram as telegram_module
from echobot.app.services.channel_runtime_manager import ChannelRuntimeManager
from echobot.app.services.channels import ChannelActivationError, ChannelService
from echobot.channels import ChannelManager, ChannelsConfig, MessageBus
from echobot.channels.base import BaseChannel
from echobot.channels.config import load_channels_config
from echobot.channels.platforms.telegram import TelegramChannel


class TelegramChannelLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_stays_false_until_polling_is_ready(self) -> None:
        app = _FakeTelegramApplication()
        channel = TelegramChannel(_telegram_config(), MessageBus())

        with _patched_telegram_runtime(app):
            start_task = asyncio.create_task(channel.start())
            try:
                await asyncio.wait_for(app.initialize_entered.wait(), timeout=0.2)
                self.assertFalse(channel.is_running)

                app.allow_initialize.set()
                await asyncio.wait_for(app.updater.polling_started.wait(), timeout=0.2)
                self.assertTrue(channel.is_running)
            finally:
                app.allow_initialize.set()
                start_task.cancel()
                await asyncio.gather(start_task, return_exceptions=True)

        self.assertFalse(channel.is_running)
        self.assertIsNone(channel._app)

    async def test_failed_initialization_leaves_channel_stopped_and_clean(self) -> None:
        app = _FakeTelegramApplication(
            initialize_error=RuntimeError("telegram initialization failed"),
        )
        app.allow_initialize.set()
        channel = TelegramChannel(_telegram_config(), MessageBus())

        with _patched_telegram_runtime(app):
            with self.assertRaisesRegex(RuntimeError, "initialization failed"):
                await channel.start()

        self.assertFalse(channel.is_running)
        self.assertIsNone(channel._app)
        self.assertEqual(1, app.shutdown_calls)


class ChannelRuntimeManagerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_reload_stops_previous_manager_before_starting_replacement(
        self,
    ) -> None:
        events: list[str] = []
        active_managers = {"previous"}
        previous_manager = _LifecycleChannelManager(
            "previous",
            events,
            active_managers,
        )
        replacement_manager = _LifecycleChannelManager(
            "replacement",
            events,
            active_managers,
        )
        runtime_manager = ChannelRuntimeManager(
            config_path=Path("unused-channels.json"),
            bus=MessageBus(),
            attachment_store=None,
        )
        runtime_manager.channel_manager = previous_manager
        runtime_manager.channels_config = ChannelsConfig()
        replacement_config = ChannelsConfig()

        with patch(
            "echobot.app.services.channel_runtime_manager.ChannelManager",
            return_value=replacement_manager,
        ):
            await runtime_manager.reload(replacement_config)

        self.assertEqual(["previous.stop", "replacement.start"], events)
        self.assertFalse(replacement_manager.overlap_detected)
        self.assertIs(replacement_manager, runtime_manager.channel_manager)
        self.assertIs(replacement_config, runtime_manager.channels_config)

    async def test_reload_restores_previous_manager_when_replacement_start_fails(
        self,
    ) -> None:
        events: list[str] = []
        active_managers = {"previous"}
        previous_manager = _LifecycleChannelManager(
            "previous",
            events,
            active_managers,
        )
        replacement_manager = _LifecycleChannelManager(
            "replacement",
            events,
            active_managers,
            start_error=RuntimeError("replacement start failed"),
        )
        runtime_manager = ChannelRuntimeManager(
            config_path=Path("unused-channels.json"),
            bus=MessageBus(),
            attachment_store=None,
        )
        previous_config = ChannelsConfig()
        replacement_config = ChannelsConfig()
        runtime_manager.channel_manager = previous_manager
        runtime_manager.channels_config = previous_config

        with patch(
            "echobot.app.services.channel_runtime_manager.ChannelManager",
            return_value=replacement_manager,
        ):
            with self.assertRaisesRegex(RuntimeError, "replacement start failed"):
                await runtime_manager.reload(replacement_config)

        self.assertEqual(
            [
                "previous.stop",
                "replacement.start",
                "replacement.stop",
                "previous.start",
            ],
            events,
        )
        self.assertTrue(previous_manager.is_available)
        self.assertEqual({"previous"}, active_managers)
        self.assertIs(previous_manager, runtime_manager.channel_manager)
        self.assertIs(previous_config, runtime_manager.channels_config)


class ChannelManagerStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_all_reports_background_channel_startup_failure(self) -> None:
        config = ChannelsConfig(
            configs={"failing": SimpleNamespace(enabled=True)},
        )
        definition = SimpleNamespace(channel_cls=_AsyncFailingChannel)

        with patch(
            "echobot.channels.manager.get_channel_registry",
            return_value={"failing": definition},
        ):
            manager = ChannelManager(config, MessageBus())
            with self.assertRaisesRegex(
                RuntimeError,
                r"Channel failing failed to start \(RuntimeError\)",
            ):
                await manager.start_all()

        self.assertFalse(manager._started)
        self.assertEqual({}, manager._channel_tasks)

    async def test_failed_activation_does_not_persist_replacement_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "channels.json"
            initial = load_channels_config(config_path)
            self.assertFalse(initial.console.enabled)

            async def fail_reload(_config: ChannelsConfig) -> None:
                raise RuntimeError("secret-bearing-provider-error")

            service = ChannelService(
                config_path=config_path,
                get_status=lambda: {},
                reload_channels=fail_reload,
            )
            with self.assertRaisesRegex(
                ChannelActivationError,
                "previous runtime remains active",
            ) as raised:
                await service.update_config(
                    {"console": {"enabled": True}},
                )

            persisted = load_channels_config(config_path)
            self.assertFalse(persisted.console.enabled)
            self.assertNotIn("secret-bearing-provider-error", str(raised.exception))


def _telegram_config() -> SimpleNamespace:
    return SimpleNamespace(
        allow_from=[],
        bot_token="telegram-test-token",
        drop_pending_updates=True,
        proxy="",
        reply_to_message=False,
    )


def _patched_telegram_runtime(app: "_FakeTelegramApplication"):
    builder = _FakeTelegramApplicationBuilder(app)
    return _TelegramRuntimePatches(builder)


class _TelegramRuntimePatches:
    def __init__(self, builder: "_FakeTelegramApplicationBuilder") -> None:
        self._patches = (
            patch.object(telegram_module, "TELEGRAM_AVAILABLE", True),
            patch.object(telegram_module, "HTTPXRequest", return_value=object()),
            patch.object(
                telegram_module,
                "Application",
                SimpleNamespace(builder=lambda: builder),
            ),
            patch.object(telegram_module, "MessageHandler", return_value=object()),
            patch.object(
                telegram_module,
                "filters",
                SimpleNamespace(ALL=object()),
            ),
        )

    def __enter__(self) -> None:
        for runtime_patch in self._patches:
            runtime_patch.start()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        for runtime_patch in reversed(self._patches):
            runtime_patch.stop()


class _FakeTelegramApplicationBuilder:
    def __init__(self, app: "_FakeTelegramApplication") -> None:
        self.app = app

    def token(self, _token: str) -> "_FakeTelegramApplicationBuilder":
        return self

    def request(self, _request) -> "_FakeTelegramApplicationBuilder":
        return self

    def get_updates_request(self, _request) -> "_FakeTelegramApplicationBuilder":
        return self

    def proxy(self, _proxy: str) -> "_FakeTelegramApplicationBuilder":
        return self

    def get_updates_proxy(self, _proxy: str) -> "_FakeTelegramApplicationBuilder":
        return self

    def build(self) -> "_FakeTelegramApplication":
        return self.app


class _FakeTelegramApplication:
    def __init__(self, *, initialize_error: Exception | None = None) -> None:
        self.initialize_error = initialize_error
        self.initialize_entered = asyncio.Event()
        self.allow_initialize = asyncio.Event()
        self.bot = _FakeTelegramBot()
        self.updater = _FakeTelegramUpdater()
        self.shutdown_calls = 0

    def add_error_handler(self, _handler) -> None:
        return None

    def add_handler(self, _handler) -> None:
        return None

    async def initialize(self) -> None:
        self.initialize_entered.set()
        await self.allow_initialize.wait()
        if self.initialize_error is not None:
            raise self.initialize_error

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


class _FakeTelegramBot:
    async def set_my_commands(self, _commands) -> None:
        return None


class _FakeTelegramUpdater:
    def __init__(self) -> None:
        self.polling_started = asyncio.Event()

    async def start_polling(self, **_kwargs) -> None:
        self.polling_started.set()

    async def stop(self) -> None:
        return None


class _LifecycleChannelManager:
    def __init__(
        self,
        name: str,
        events: list[str],
        active_managers: set[str],
        *,
        start_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.events = events
        self.active_managers = active_managers
        self.start_error = start_error
        self.is_available = name in active_managers
        self.overlap_detected = False

    async def start_all(self) -> None:
        self.events.append(f"{self.name}.start")
        if self.start_error is not None:
            raise self.start_error
        self.overlap_detected = bool(self.active_managers)
        self.active_managers.add(self.name)
        self.is_available = True

    async def stop_all(self) -> None:
        self.events.append(f"{self.name}.stop")
        self.active_managers.discard(self.name)
        self.is_available = False


class _AsyncFailingChannel(BaseChannel):
    name = "failing"

    async def start(self) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("asynchronous startup failed")

    async def stop(self) -> None:
        self._running = False

    async def send(self, _message) -> None:
        return None

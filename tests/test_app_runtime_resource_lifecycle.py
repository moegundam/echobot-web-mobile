from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from echobot.app.runtime import AppRuntime, AppRuntimeStopError
from echobot.app.services.stage_event_redis import RedisStreamsStageEventBroker
from echobot.app.services.user_scoped_runtime import (
    UserScopedRuntime,
    UserScopedRuntimeStopError,
)
from echobot.cli.chat import CliRuntimeCleanupError, cleanup_cli_runtime_resources
from echobot.runtime.bootstrap import RuntimeOptions


class _AsyncResource:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    async def close(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


class _StopResource:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    async def stop_all(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


class _ChannelManagerResource:
    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


class _ServiceStopResource:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    async def stop(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


class _SyncCloseResource:
    def __init__(self) -> None:
        self.calls = 0

    def close(self) -> None:
        self.calls += 1


class _SessionContext:
    def __init__(self, coordinator: _AsyncResource) -> None:
        self.coordinator = coordinator
        self.store_close_calls = 0

    def close_session_stores(self) -> None:
        self.store_close_calls += 1


class AppRuntimeResourceLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_cleanup_attempts_every_resource_after_stop_failure(self) -> None:
        cron = _ServiceStopResource(error=RuntimeError("cron stop failed"))
        heartbeat = _ServiceStopResource()
        coordinator = _AsyncResource()
        memory = _AsyncResource()
        session_store = _SyncCloseResource()
        agent_session_store = _SyncCloseResource()
        context = SimpleNamespace(
            cron_service=cron,
            heartbeat_service=heartbeat,
            memory_support=memory,
            session_store=session_store,
            agent_session_store=agent_session_store,
        )

        with self.assertRaises(CliRuntimeCleanupError) as raised:
            await cleanup_cli_runtime_resources(context, coordinator)

        self.assertIn("cron stop failed", str(raised.exception))
        self.assertEqual(1, heartbeat.calls)
        self.assertEqual(1, coordinator.calls)
        self.assertEqual(1, memory.calls)
        self.assertEqual(1, session_store.calls)
        self.assertEqual(1, agent_session_store.calls)

    async def test_app_start_failure_rolls_back_every_partial_resource(self) -> None:
        coordinator = _AsyncResource()
        context = _SessionContext(coordinator)
        context.workspace = Path(".")
        context.storage_root = None
        context.attachment_store = object()
        context.memory_support = _AsyncResource()
        channels = _ChannelManagerResource()
        tts = _AsyncResource()
        asr = _AsyncResource()
        stage_broker = _AsyncResource()
        user_factory = _StopResource()
        runtime = AppRuntime(
            runtime_options=RuntimeOptions(workspace=Path(".")),
            channel_config_path=".echobot/channels.json",
            context_builder=lambda _options: context,
            tts_service_builder=lambda _workspace: tts,
            asr_service_builder=lambda _workspace: asr,
        )
        runtime.stage_event_broker = stage_broker
        runtime.user_runtime_factory = user_factory

        with (
            patch(
                "echobot.app.runtime.ChannelRuntimeManager",
                return_value=channels,
            ),
            patch(
                "echobot.app.runtime.build_runtime_composition",
                side_effect=RuntimeError("composition failed"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "composition failed"):
                await runtime.start()

        self.assertEqual(1, channels.stop_calls)
        self.assertEqual(1, user_factory.calls)
        self.assertEqual(1, coordinator.calls)
        self.assertEqual(1, context.memory_support.calls)
        self.assertEqual(1, context.store_close_calls)
        self.assertEqual(1, tts.calls)
        self.assertEqual(1, asr.calls)
        self.assertEqual(1, stage_broker.calls)
        self.assertFalse(runtime._started)

    async def test_user_runtime_start_failure_rolls_back_partial_resources(self) -> None:
        coordinator = _AsyncResource()
        context = _SessionContext(coordinator)
        context.workspace = Path(".")
        context.memory_support = _AsyncResource()
        tts = _AsyncResource()
        asr = _AsyncResource()
        parent = SimpleNamespace(
            context=object(),
            runtime_options=RuntimeOptions(workspace=Path(".")),
            _context_builder=lambda _options: context,
            _tts_service_builder=lambda _workspace: tts,
            _asr_service_builder=lambda _workspace: asr,
            model_profile_service=None,
            character_profile_settings_service=None,
            stage_event_broker=object(),
        )
        runtime = UserScopedRuntime(
            parent=parent,
            user_id="operator@example.test",
            storage_root=Path(".echobot/users/operator"),
        )

        with patch(
            "echobot.app.services.user_scoped_runtime.build_runtime_composition",
            side_effect=RuntimeError("composition failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "composition failed"):
                await runtime.start()

        self.assertEqual(1, coordinator.calls)
        self.assertEqual(1, context.memory_support.calls)
        self.assertEqual(1, context.store_close_calls)
        self.assertEqual(1, tts.calls)
        self.assertEqual(1, asr.calls)
        self.assertFalse(runtime._started)

    async def test_stop_closes_session_stores_and_owned_stage_broker(self) -> None:
        runtime, resources = _runtime_stub()

        await AppRuntime.stop(runtime)
        await AppRuntime.stop(runtime)

        self.assertEqual(1, resources.context.store_close_calls)
        self.assertEqual(1, resources.stage_broker.calls)
        self.assertEqual(1, resources.tts.calls)
        self.assertEqual(1, resources.asr.calls)
        self.assertFalse(runtime._started)

    async def test_stop_attempts_all_cleanup_after_an_earlier_failure(self) -> None:
        runtime, resources = _runtime_stub(
            user_runtime_error=RuntimeError("user runtime stop failed"),
        )

        with self.assertRaises(AppRuntimeStopError) as raised:
            await AppRuntime.stop(runtime)

        self.assertIn("user runtime stop failed", str(raised.exception))
        self.assertEqual(1, resources.context.store_close_calls)
        self.assertEqual(1, resources.stage_broker.calls)
        self.assertEqual(1, resources.tts.calls)
        self.assertEqual(1, resources.asr.calls)
        self.assertFalse(runtime._started)

    async def test_redis_broker_only_closes_clients_it_owns(self) -> None:
        owned_client = _AsyncResource()
        owned = RedisStreamsStageEventBroker(redis_url="redis://stage.test/0")
        owned._client = owned_client

        injected_client = _AsyncResource()
        injected = RedisStreamsStageEventBroker(client=injected_client)

        factory_client = _AsyncResource()
        factory_owned = RedisStreamsStageEventBroker(
            client_factory=lambda: factory_client,
        )
        await factory_owned._get_client()

        await owned.close()
        await owned.close()
        await injected.close()
        await factory_owned.close()

        self.assertEqual(1, owned_client.calls)
        self.assertEqual(0, injected_client.calls)
        self.assertEqual(1, factory_client.calls)

    async def test_user_runtime_closes_stores_even_when_coordinator_close_fails(self) -> None:
        coordinator = _AsyncResource(error=RuntimeError("coordinator failed"))
        context = _SessionContext(coordinator)
        tts = _AsyncResource()
        asr = _AsyncResource()
        runtime = object.__new__(UserScopedRuntime)
        runtime._started = True
        runtime.context = context
        runtime.tts_service = tts
        runtime.asr_service = asr

        with self.assertRaises(UserScopedRuntimeStopError):
            await UserScopedRuntime.stop(runtime)

        self.assertEqual(1, context.store_close_calls)
        self.assertEqual(1, tts.calls)
        self.assertEqual(1, asr.calls)
        self.assertFalse(runtime._started)


def _runtime_stub(
    *,
    user_runtime_error: Exception | None = None,
) -> tuple[AppRuntime, SimpleNamespace]:
    runtime = object.__new__(AppRuntime)
    coordinator = _AsyncResource()
    context = _SessionContext(coordinator)
    stage_broker = _AsyncResource()
    tts = _AsyncResource()
    asr = _AsyncResource()
    user_factory = _StopResource(error=user_runtime_error)

    runtime._started = True
    runtime.gateway_task = None
    runtime.channel_runtime_manager = None
    runtime.user_runtime_factory = user_factory
    runtime.context = context
    runtime.tts_service = tts
    runtime.asr_service = asr
    runtime.stage_event_broker = stage_broker

    return runtime, SimpleNamespace(
        context=context,
        stage_broker=stage_broker,
        tts=tts,
        asr=asr,
        user_factory=user_factory,
    )


if __name__ == "__main__":
    unittest.main()

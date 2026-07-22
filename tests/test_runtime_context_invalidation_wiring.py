from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from echobot.app.services.character_profile_application import (
    CharacterProfileApplicationService,
)
from echobot.app.services.runtime_catalog_application import (
    RuntimeCatalogApplicationService,
)
from echobot.app.services.runtime_context_cache import get_runtime_context_cache
from echobot.app.services.runtime_context_events import (
    notify_roles_runtime_context_changed,
    notify_runtime_tree_contexts_changed,
    notify_session_runtime_context_changed,
)
from echobot.app.services.session_application import SessionApplicationService
from echobot.app.services.stage_events import StageEventBroker
from echobot.app.auth import user_storage_key


class _SessionService:
    def __init__(self, sessions):
        self.sessions = sessions

    async def list_sessions(self):
        return self.sessions


class _FailingBroker:
    async def publish(self, **_kwargs):
        raise RuntimeError("broker unavailable")


class _OverrideService:
    def __init__(self):
        self.values = {}

    def get_override(self, session_name):
        return dict(self.values.get(session_name, {}))

    def set_override(self, session_name, payload):
        self.values[session_name] = dict(payload)

    def clear_profile_references(self, _profile_id, _field_names):
        return None


class _AsyncLock:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, *_args):
        self._lock.release()

    @property
    def locked(self):
        return self._lock.locked()


class RuntimeContextInvalidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_contract_is_scoped_and_publish_failure_is_best_effort(self):
        runtime = SimpleNamespace(
            stage_event_broker=StageEventBroker(),
            session_service=_SessionService(
                [
                    SimpleNamespace(name="alpha", metadata={"role_name": "host"}),
                    SimpleNamespace(name="beta", metadata={"role_name": "other"}),
                ],
            ),
            user_id="operator-a",
        )

        revision = await notify_session_runtime_context_changed(
            runtime,
            "alpha",
            reason="session_route_mode_updated",
        )
        scope_key = user_storage_key("operator-a")
        event = runtime.stage_event_broker.history(scope_key, "alpha")[0]

        self.assertEqual("", event.text)
        self.assertEqual(revision, event.metadata["revision"])
        self.assertEqual("session_route_mode_updated", event.metadata["reason"])
        self.assertEqual(1, event.metadata["schema_version"])
        self.assertEqual([], runtime.stage_event_broker.history(scope_key, "beta"))

        runtime.stage_event_broker = _FailingBroker()
        next_revision = await notify_session_runtime_context_changed(
            runtime,
            "alpha",
            reason="session_channel_binding_updated",
        )
        self.assertNotEqual(revision, next_revision)
        self.assertEqual(
            next_revision,
            await get_runtime_context_cache(runtime).current_revision("alpha"),
        )

    async def test_role_invalidation_only_notifies_effective_role_sessions(self):
        override_service = _OverrideService()
        override_service.values["beta"] = {"role_name": "host"}
        runtime = SimpleNamespace(
            stage_event_broker=StageEventBroker(),
            session_service=_SessionService(
                [
                    SimpleNamespace(name="alpha", metadata={"role_name": "host"}),
                    SimpleNamespace(name="beta", metadata={"role_name": "other"}),
                    SimpleNamespace(name="gamma", metadata={"role_name": "other"}),
                ],
            ),
            session_runtime_override_service=override_service,
            user_id="operator-a",
        )

        revisions = await notify_roles_runtime_context_changed(
            runtime,
            {"host"},
            reason="character_prompt_updated",
        )

        self.assertEqual({"alpha", "beta"}, set(revisions))
        scope_key = user_storage_key("operator-a")
        self.assertEqual(1, len(runtime.stage_event_broker.history(scope_key, "alpha")))
        self.assertEqual(1, len(runtime.stage_event_broker.history(scope_key, "beta")))
        self.assertEqual([], runtime.stage_event_broker.history(scope_key, "gamma"))

    async def test_owner_global_change_notifies_parent_and_cached_user_runtimes(self):
        broker = StageEventBroker()
        parent = SimpleNamespace(
            stage_event_broker=broker,
            session_service=_SessionService([SimpleNamespace(name="root")]),
            user_id="",
        )
        alpha = SimpleNamespace(
            parent=parent,
            stage_event_broker=broker,
            session_service=_SessionService([SimpleNamespace(name="alpha")]),
            user_id="alpha@example.test",
        )
        beta = SimpleNamespace(
            parent=parent,
            stage_event_broker=broker,
            session_service=_SessionService([SimpleNamespace(name="beta")]),
            user_id="beta@example.test",
        )
        parent.user_runtime_factory = SimpleNamespace(
            cached_runtimes=lambda: (alpha, beta),
        )

        await notify_runtime_tree_contexts_changed(
            alpha,
            reason="channel_config_updated",
        )

        self.assertEqual(1, len(broker.history("default", "root")))
        self.assertEqual(
            1,
            len(broker.history(user_storage_key(alpha.user_id), "alpha")),
        )
        self.assertEqual(
            1,
            len(broker.history(user_storage_key(beta.user_id), "beta")),
        )

    async def test_session_mutations_notify_only_after_success(self):
        runtime = SimpleNamespace(
            session_binding_lock=_AsyncLock(),
            session_service=SimpleNamespace(),
            chat_service=SimpleNamespace(
                set_route_mode=AsyncMock(
                    return_value=SimpleNamespace(name="demo"),
                ),
            ),
        )
        service = SessionApplicationService(runtime)

        with patch(
            "echobot.app.services.session_application.notify_session_runtime_context_changed",
            new=AsyncMock(),
        ) as notify:
            result = await service.set_route_mode("demo", "chat_only")

        self.assertEqual("demo", result.name)
        notify.assert_awaited_once_with(
            runtime,
            "demo",
            reason="session_route_mode_updated",
        )

        runtime.chat_service.set_route_mode.side_effect = ValueError("invalid mode")
        with patch(
            "echobot.app.services.session_application.notify_session_runtime_context_changed",
            new=AsyncMock(),
        ) as failed_notify:
            with self.assertRaises(ValueError):
                await service.set_route_mode("demo", "invalid")
        failed_notify.assert_not_awaited()

    async def test_session_configuration_publishes_after_releasing_mutation_lock(self):
        mutation_lock = _AsyncLock()
        runtime = SimpleNamespace(
            session_binding_lock=mutation_lock,
            context=SimpleNamespace(
                role_registry=SimpleNamespace(
                    require=lambda _name: SimpleNamespace(name="default"),
                ),
            ),
            session_service=SimpleNamespace(
                load_session=AsyncMock(return_value=SimpleNamespace(name="demo")),
                update_session_metadata=AsyncMock(
                    return_value=SimpleNamespace(name="demo"),
                ),
            ),
        )

        async def assert_lock_released(*_args, **_kwargs):
            self.assertFalse(mutation_lock.locked)

        with patch(
            "echobot.app.services.session_application.notify_session_runtime_context_changed",
            new=AsyncMock(side_effect=assert_lock_released),
        ) as notify:
            result = await SessionApplicationService(runtime).update_configuration(
                "demo",
                role_name="default",
                route_mode="chat_only",
                channel_type="",
                channel_integration_id="",
            )

        self.assertEqual("demo", result.name)
        notify.assert_awaited_once()

    async def test_override_and_catalog_mutations_use_targeted_and_global_notifiers(self):
        override_service = _OverrideService()
        runtime = SimpleNamespace(
            session_service=SimpleNamespace(
                load_session=AsyncMock(return_value=SimpleNamespace(name="demo")),
            ),
            session_runtime_override_service=override_service,
            model_profile_service=object(),
            context=SimpleNamespace(role_registry=SimpleNamespace(require=lambda _name: None)),
            character_profile_settings_service=None,
            llm_model_service=SimpleNamespace(
                delete_model=lambda _model_id: {"models": []},
            ),
            stage_event_broker=StageEventBroker(),
            user_id="operator-a",
        )

        with (
            patch(
                "echobot.app.services.runtime_catalog_application.ensure_runtime_services_ready",
            ),
            patch(
                "echobot.app.services.runtime_catalog_application.runtime_profile_payload",
                new=AsyncMock(return_value={"profiles": []}),
            ),
            patch(
                "echobot.app.services.runtime_catalog_application.validate_runtime_profile_ids",
            ),
            patch(
                "echobot.app.services.runtime_catalog_application.apply_runtime_override_if_current_session",
                new=AsyncMock(),
            ),
            patch(
                "echobot.app.services.runtime_catalog_application.notify_session_runtime_context_changed",
                new=AsyncMock(),
            ) as session_notify,
            patch(
                "echobot.app.services.runtime_catalog_application.notify_all_runtime_contexts_changed",
                new=AsyncMock(),
            ) as global_notify,
        ):
            resolved = await RuntimeCatalogApplicationService(runtime).update_session_runtime_overrides(
                "demo",
                {"route_mode": "chat_only"},
            )
            deleted = await RuntimeCatalogApplicationService(runtime).delete_llm_model("llm-a")

        self.assertEqual("demo", resolved)
        self.assertEqual({"models": []}, deleted)
        session_notify.assert_awaited_once_with(
            runtime,
            "demo",
            reason="session_runtime_override_updated",
        )
        global_notify.assert_awaited_once_with(
            runtime,
            reason="llm_catalog_updated",
        )

    async def test_character_mutation_notifies_after_state_is_built(self):
        card = SimpleNamespace(name="host", prompt="prompt")
        runtime = SimpleNamespace(
            role_service=SimpleNamespace(create_role=AsyncMock(return_value=card)),
            character_profile_settings_service=SimpleNamespace(
                set_emotion_maps=lambda *_args: None,
            ),
            session_service=None,
            context=None,
        )
        service = CharacterProfileApplicationService(runtime)
        service._set_runtime_bindings_from_payload = AsyncMock()
        service._set_or_clear_binding = AsyncMock(return_value={"profiles": []})
        service._state = AsyncMock(return_value="state")

        with patch(
            "echobot.app.services.character_profile_application.notify_roles_runtime_context_changed",
            new=AsyncMock(),
        ) as notify:
            result = await service.create({"name": "Host", "prompt": "prompt"})

        self.assertEqual("state", result)
        notify.assert_awaited_once_with(
            runtime,
            {"host"},
            reason="character_runtime_binding_created",
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...asr import ASRService
from ...channels import ChannelsConfig, OutboundMessage
from ...concurrency import AsyncReentrantLock
from ...gateway import DeliveryStore, GatewaySessionService, RouteSessionStore
from ...runtime.bootstrap import RuntimeContext
from ...tts import TTSService
from ..auth import TrustedUserConfig, user_storage_key
from .chat import ChatService
from .character_profiles import CharacterProfileSettingsService
from .live2d_models import Live2DModelService
from .llm_models import LLMModelService
from .model_profiles import ModelProfileService
from .roles import RoleService
from .runtime_composition import build_runtime_composition
from .runtime_context_events import notify_session_runtime_context_changed
from .runtime_model_services import active_runtime_profile
from .runtime_profile_applier import RuntimeProfileApplier
from .session_runtime_overrides import SessionRuntimeOverrideService
from .session_turn_runtime import resolve_session_turn_runtime
from .stage_events import StageEventBrokerProtocol
from .voice_models import VoiceModelService
from .web_console import WebConsoleService

if TYPE_CHECKING:
    from ..runtime import AppRuntime


logger = logging.getLogger(__name__)


class UserScopedRuntimeStopError(RuntimeError):
    """Reports user-runtime cleanup failures after all resources are attempted."""

    def __init__(self, failures: list[tuple[str, Exception]]) -> None:
        self.failures = tuple(failures)
        details = "; ".join(
            f"{name}: {type(error).__name__}: {error}"
            for name, error in failures
        )
        super().__init__(f"User runtime cleanup failed: {details}")


class UserScopedRuntime:
    def __init__(
        self,
        *,
        parent: AppRuntime,
        user_id: str,
        storage_root: Path,
    ) -> None:
        self.parent = parent
        self.user_id = user_id
        self.storage_root = storage_root
        self.context: RuntimeContext | None = None
        self.delivery_store: DeliveryStore | None = None
        self.route_session_store: RouteSessionStore | None = None
        self.session_service: GatewaySessionService | None = None
        self.chat_service: ChatService | None = None
        self.role_service: RoleService | None = None
        self.character_profile_settings_service: CharacterProfileSettingsService | None = None
        self.model_profile_service: ModelProfileService | None = None
        self.llm_model_service: LLMModelService | None = None
        self.voice_model_service: VoiceModelService | None = None
        self.live2d_model_service: Live2DModelService | None = None
        self.web_console_service: WebConsoleService | None = None
        self.runtime_profile_applier: RuntimeProfileApplier | None = None
        self.last_applied_model_profile: dict[str, object] = {}
        self.model_profile_lock = AsyncReentrantLock()
        self.model_profile_revision = 0
        self.stage_event_broker: StageEventBrokerProtocol = parent.stage_event_broker
        self.session_binding_lock = asyncio.Lock()
        self.session_runtime_override_service = SessionRuntimeOverrideService()
        self.tts_service: TTSService | None = None
        self.asr_service: ASRService | None = None
        self._started = False

    @property
    def workspace(self) -> Path:
        if self.context is None:
            raise RuntimeError("App runtime has not been started")
        return self.context.workspace

    async def start(self) -> None:
        if self._started:
            return

        try:
            await self._start_resources()
        except BaseException:
            self._started = True
            try:
                await self.stop()
            except Exception:
                logger.exception("Failed to fully roll back user runtime startup")
            raise

    async def _start_resources(self) -> None:
        if self.parent.context is None:
            raise RuntimeError("Parent app runtime has not been started")

        options = replace(
            self.parent.runtime_options,
            storage_root=self.storage_root,
            tool_workspace=self.storage_root / "workspace",
            memory_workspace=self.storage_root / "memory",
        )
        self.context = self.parent._context_builder(options)
        self.asr_service = self.parent._asr_service_builder(self.context.workspace)
        self.tts_service = self.parent._tts_service_builder(self.context.workspace)
        composition = build_runtime_composition(
            context=self.context,
            storage_root=self.storage_root,
            tts_service=self.tts_service,
            asr_service=self.asr_service,
            model_profile_seed=self.parent.model_profile_service,
            character_profile_seed=self.parent.character_profile_settings_service,
        )
        composition.install_on(self)
        self.context.coordinator.set_turn_runtime_resolver(
            lambda session_name, role_name: resolve_session_turn_runtime(
                self,
                session_name,
                role_name,
            )
        )
        await composition.initialize_speech()
        await self.apply_active_model_profile()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        failures: list[tuple[str, Exception]] = []
        if self.context is not None:
            await _attempt_async_cleanup(
                failures,
                "coordinator",
                self.context.coordinator.close,
            )
            memory_support = getattr(self.context, "memory_support", None)
            if memory_support is not None:
                await _attempt_async_cleanup(
                    failures,
                    "memory",
                    memory_support.close,
                )
        if self.tts_service is not None:
            await _attempt_async_cleanup(failures, "tts", self.tts_service.close)
        if self.asr_service is not None:
            await _attempt_async_cleanup(failures, "asr", self.asr_service.close)
        if self.context is not None:
            try:
                self.context.close_session_stores()
            except Exception as exc:
                failures.append(("session repositories", exc))
        self._started = False
        if failures:
            raise UserScopedRuntimeStopError(failures)

    def channel_status(self) -> dict[str, dict[str, bool]]:
        return self.parent.channel_status()

    async def publish_gateway_stage_event(
        self,
        session_name: str,
        outbound: OutboundMessage,
    ) -> None:
        scope_key = _user_stage_scope_key(self.user_id)
        await self.parent.stage_event_publisher.publish_gateway_event(
            channels_config=self.parent.channels_config,
            scope_key=scope_key,
            session_name=session_name,
            outbound=outbound,
        )
        if not TrustedUserConfig.from_env().enabled and scope_key != "default":
            await self.parent.stage_event_publisher.publish_gateway_event(
                channels_config=self.parent.channels_config,
                scope_key="default",
                session_name=session_name,
                outbound=outbound,
            )

    async def notify_session_runtime_context_changed(
        self,
        session_name: str,
        reason: str,
    ) -> None:
        await notify_session_runtime_context_changed(
            self,
            session_name,
            reason=reason,
        )

    async def reload_channels(
        self,
        config: ChannelsConfig | None = None,
    ) -> None:
        await self.parent.reload_channels(config)

    async def health_snapshot(self) -> dict[str, object]:
        if self.context is None or self.session_service is None:
            raise RuntimeError("App runtime has not been started")

        current_session = await self.session_service.load_current_session()
        current_role = await self.context.coordinator.current_role_name(
            current_session.name,
        )
        job_counts = await self.context.coordinator.job_counts()
        return {
            "status": "ok",
            "workspace_name": self.context.workspace.name,
            "storage_scope": "user",
            "trusted_user": self.user_id,
            "current_session": current_session.name,
            "current_role": current_role,
            "channels": self.channel_status(),
            "bus": {
                "inbound_size": (
                    self.parent.bus.inbound_size if self.parent.bus is not None else 0
                ),
                "outbound_size": (
                    self.parent.bus.outbound_size if self.parent.bus is not None else 0
                ),
            },
            "jobs": job_counts,
        }

    async def apply_active_model_profile(self) -> None:
        if self.model_profile_service is None:
            return
        await self.apply_model_profile(active_runtime_profile(self))

    async def apply_model_profile(self, profile: dict[str, object]) -> None:
        async with self.model_profile_lock:
            if self.runtime_profile_applier is not None:
                await self.runtime_profile_applier.apply(profile)
            self.last_applied_model_profile = deepcopy(profile)
            self.model_profile_revision += 1


async def _attempt_async_cleanup(
    failures: list[tuple[str, Exception]],
    name: str,
    cleanup: Callable[[], Awaitable[None]],
) -> None:
    try:
        await cleanup()
    except Exception as exc:
        failures.append((name, exc))


def _user_stage_scope_key(user_id: str) -> str:
    return user_storage_key(user_id) if user_id else "default"

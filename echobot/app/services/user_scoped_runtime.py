from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...asr import ASRService
from ...channels import ChannelsConfig, OutboundMessage
from ...concurrency import AsyncReentrantLock
from ...gateway import DeliveryStore, GatewaySessionService, RouteSessionStore
from ...runtime.bootstrap import RuntimeContext
from ...runtime.session_service import SessionLifecycleService
from ...tts import TTSService
from ..auth import TrustedUserConfig, user_storage_key
from .chat import ChatService
from .character_profiles import CharacterProfileSettingsService
from .live2d_models import Live2DModelService
from .llm_models import LLMModelService
from .model_profiles import ModelProfileService
from .roles import RoleService
from .runtime_model_services import active_runtime_profile, build_runtime_model_services
from .runtime_profile_applier import RuntimeProfileApplier
from .session_runtime_overrides import SessionRuntimeOverrideService
from .stage_events import StageEventBroker
from .voice_models import VoiceModelService
from .web_console import WebConsoleService

if TYPE_CHECKING:
    from ..runtime import AppRuntime


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
        self.stage_event_broker: StageEventBroker = parent.stage_event_broker
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
        if self.parent.context is None:
            raise RuntimeError("Parent app runtime has not been started")

        options = replace(
            self.parent.runtime_options,
            storage_root=self.storage_root,
        )
        self.context = self.parent._context_builder(options)
        self.delivery_store = DeliveryStore(self.storage_root / "delivery.json")
        self.route_session_store = RouteSessionStore(
            self.storage_root / "route_sessions.json",
        )
        core_session_service = SessionLifecycleService(
            self.context.session_store,
            self.context.agent_session_store,
            coordinator=self.context.coordinator,
        )
        self.session_service = GatewaySessionService(
            core_session_service,
            route_session_store=self.route_session_store,
            delivery_store=self.delivery_store,
        )
        self.chat_service = ChatService(self.context.coordinator)
        self.role_service = RoleService(
            self.context.role_registry,
            self.context.session_store,
        )
        self.character_profile_settings_service = CharacterProfileSettingsService(
            self.storage_root,
        )
        if self.parent.character_profile_settings_service is not None:
            self.character_profile_settings_service.seed_from(
                self.parent.character_profile_settings_service,
            )
        self.model_profile_service = ModelProfileService(self.storage_root)
        if self.parent.model_profile_service is not None:
            self.model_profile_service.seed_from(self.parent.model_profile_service)
        (
            self.llm_model_service,
            self.voice_model_service,
            self.live2d_model_service,
        ) = build_runtime_model_services(self.model_profile_service)
        self.asr_service = self.parent._asr_service_builder(self.context.workspace)
        self.tts_service = self.parent._tts_service_builder(self.context.workspace)
        self.web_console_service = WebConsoleService(
            self.context.workspace,
            self.tts_service,
            self.asr_service,
            storage_root=self.storage_root,
        )
        self.runtime_profile_applier = RuntimeProfileApplier(
            context=self.context,
            web_console_service=self.web_console_service,
        )
        asr_initialized = await self.web_console_service.initialize_runtime_settings()
        if not asr_initialized:
            await self.asr_service.on_startup()
        await self.apply_active_model_profile()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        if self.context is not None:
            await self.context.coordinator.close()
        if self.tts_service is not None:
            await self.tts_service.close()
        if self.asr_service is not None:
            await self.asr_service.close()
        self._started = False

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


def _user_stage_scope_key(user_id: str) -> str:
    return user_storage_key(user_id) if user_id else "default"

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ..asr import (
    ASRService,
    build_default_asr_service,
)
from ..channels import (
    ChannelsConfig,
    MessageBus,
    OutboundMessage,
)
from ..gateway import (
    DeliveryStore,
    GatewayRuntime,
    GatewaySessionService,
    RouteSessionStore,
)
from ..runtime.bootstrap import RuntimeContext, RuntimeOptions, build_runtime_context
from ..runtime.session_service import SessionLifecycleService
from ..tts import TTSService, build_default_tts_service
from .services.chat import ChatService
from .services.channel_runtime_manager import ChannelRuntimeManager
from .services.character_profiles import CharacterProfileSettingsService
from .services.channels import ChannelService
from .services.live2d_models import Live2DModelService
from .services.llm_models import LLMModelService
from .services.model_profiles import ModelProfileService
from .services.roles import RoleService
from .services.runtime_model_repositories import (
    LLMModelRepository,
    Live2DModelRepository,
    VoiceModelRepository,
)
from .services.runtime_profile_applier import RuntimeProfileApplier
from .services.session_runtime_overrides import SessionRuntimeOverrideService
from .services.stage_event_publisher import StageEventPublisher
from .services.stage_events import StageEventBroker
from .services.user_runtime_factory import UserRuntimeFactory
from .services.voice_models import VoiceModelService
from .services.web_console import WebConsoleService


RuntimeContextBuilder = Callable[[RuntimeOptions], RuntimeContext]
TTSServiceBuilder = Callable[[Path], TTSService]
ASRServiceBuilder = Callable[[Path], ASRService]


class AppRuntime:
    def __init__(
        self,
        *,
        runtime_options: RuntimeOptions,
        channel_config_path: str | Path,
        context_builder: RuntimeContextBuilder | None = None,
        tts_service_builder: TTSServiceBuilder | None = None,
        asr_service_builder: ASRServiceBuilder | None = None,
    ) -> None:
        self.runtime_options = runtime_options
        self.channel_config_path = _resolve_runtime_path(
            runtime_options.workspace,
            channel_config_path,
        )
        self._context_builder = context_builder or _default_context_builder
        self._tts_service_builder = tts_service_builder or _default_tts_service_builder
        self._asr_service_builder = asr_service_builder or _default_asr_service_builder

        self.context: RuntimeContext | None = None
        self.bus: MessageBus | None = None
        self.channel_runtime_manager: ChannelRuntimeManager | None = None
        self.delivery_store: DeliveryStore | None = None
        self.route_session_store: RouteSessionStore | None = None
        self.gateway: GatewayRuntime | None = None
        self.gateway_task: asyncio.Task[None] | None = None
        self.session_service: GatewaySessionService | None = None
        self.chat_service: ChatService | None = None
        self.role_service: RoleService | None = None
        self.character_profile_settings_service: CharacterProfileSettingsService | None = None
        self.model_profile_service: ModelProfileService | None = None
        self.llm_model_service: LLMModelService | None = None
        self.voice_model_service: VoiceModelService | None = None
        self.live2d_model_service: Live2DModelService | None = None
        self.channel_service: ChannelService | None = None
        self.stage_event_broker = StageEventBroker()
        self.stage_event_publisher = StageEventPublisher(self.stage_event_broker)
        self.session_runtime_override_service = SessionRuntimeOverrideService()
        self.web_console_service: WebConsoleService | None = None
        self.runtime_profile_applier: RuntimeProfileApplier | None = None
        self.tts_service: TTSService | None = None
        self.asr_service: ASRService | None = None
        self.user_runtime_factory = UserRuntimeFactory(
            workspace_getter=lambda: self.workspace,
            runtime_builder=self._build_user_runtime,
        )
        self._started = False

    @property
    def workspace(self) -> Path:
        if self.context is None:
            raise RuntimeError("App runtime has not been started")
        return self.context.workspace

    @property
    def channels_config(self) -> ChannelsConfig | None:
        if self.channel_runtime_manager is None:
            return None
        return self.channel_runtime_manager.channels_config

    async def start(self) -> None:
        if self._started:
            return

        self.context = self._context_builder(self.runtime_options)
        self.bus = MessageBus()
        self.channel_runtime_manager = ChannelRuntimeManager(
            config_path=self.channel_config_path,
            bus=self.bus,
            attachment_store=self.context.attachment_store,
        )
        await self.channel_runtime_manager.start()
        self.delivery_store = DeliveryStore(
            self.context.workspace / ".echobot" / "delivery.json",
        )
        self.route_session_store = RouteSessionStore(
            self.context.workspace / ".echobot" / "route_sessions.json",
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
        self.gateway = GatewayRuntime(
            self.context,
            self.bus,
            session_service=self.session_service,
            runtime_for_user=self.for_user,
            stage_event_publisher=self.publish_gateway_stage_event,
        )
        self.chat_service = ChatService(
            self.context.coordinator,
            self.session_service,
        )
        self.role_service = RoleService(
            self.context.role_registry,
            self.context.session_store,
        )
        self.character_profile_settings_service = CharacterProfileSettingsService(
            _context_storage_root(self.context),
        )
        self.model_profile_service = ModelProfileService(
            _context_storage_root(self.context),
        )
        (
            self.llm_model_service,
            self.voice_model_service,
            self.live2d_model_service,
        ) = _build_runtime_model_services(self.model_profile_service)
        self.channel_service = ChannelService(
            config_path=self.channel_config_path,
            get_status=self.channel_status,
            reload_channels=self.reload_channels,
        )
        self.asr_service = self._asr_service_builder(self.context.workspace)
        self.tts_service = self._tts_service_builder(self.context.workspace)
        self.web_console_service = WebConsoleService(
            self.context.workspace,
            self.tts_service,
            self.asr_service,
            storage_root=_context_storage_root(self.context),
        )
        self.runtime_profile_applier = RuntimeProfileApplier(
            context=self.context,
            web_console_service=self.web_console_service,
        )
        asr_initialized = await self.web_console_service.initialize_runtime_settings()
        if not asr_initialized:
            await self.asr_service.on_startup()
        await self.apply_active_model_profile()

        self.gateway_task = asyncio.create_task(
            self.gateway.run(),
            name="echobot_gateway_runtime",
        )
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return

        if self.gateway_task is not None:
            self.gateway_task.cancel()
            await asyncio.gather(self.gateway_task, return_exceptions=True)
            self.gateway_task = None

        if self.channel_runtime_manager is not None:
            await self.channel_runtime_manager.stop()

        await self.user_runtime_factory.stop_all()
        if self.context is not None:
            await self.context.coordinator.close()
        if self.tts_service is not None:
            await self.tts_service.close()
        if self.asr_service is not None:
            await self.asr_service.close()

        self._started = False

    async def for_user(self, user_id: str) -> "UserScopedRuntime":
        if not self._started or self.context is None:
            raise RuntimeError("App runtime has not been started")
        if self.tts_service is None or self.asr_service is None:
            raise RuntimeError("App runtime speech services are not ready")

        return await self.user_runtime_factory.for_user(user_id)

    async def _build_user_runtime(
        self,
        user_id: str,
        storage_root: Path,
    ) -> "UserScopedRuntime":
        runtime = UserScopedRuntime(
            parent=self,
            user_id=user_id,
            storage_root=storage_root,
        )
        await runtime.start()
        return runtime

    async def reload_channels(
        self,
        config: ChannelsConfig | None = None,
    ) -> None:
        if self.channel_runtime_manager is None:
            raise RuntimeError("App runtime has not been started")

        await self.channel_runtime_manager.reload(config)

    def channel_status(self) -> dict[str, dict[str, bool]]:
        if self.channel_runtime_manager is None:
            return {}
        return self.channel_runtime_manager.status()

    async def publish_gateway_stage_event(
        self,
        session_name: str,
        outbound: OutboundMessage,
    ) -> None:
        await self.stage_event_publisher.publish_gateway_event(
            channels_config=self.channels_config,
            scope_key="default",
            session_name=session_name,
            outbound=outbound,
        )

    async def health_snapshot(self) -> dict[str, object]:
        if self.context is None or self.bus is None or self.session_service is None:
            raise RuntimeError("App runtime has not been started")

        current_session = await self.session_service.load_current_session()
        current_role = await self.context.coordinator.current_role_name(
            current_session.name,
        )
        job_counts = await self.context.coordinator.job_counts()
        return {
            "status": "ok",
            "workspace": str(self.context.workspace),
            "current_session": current_session.name,
            "current_role": current_role,
            "channels": self.channel_status(),
            "bus": {
                "inbound_size": self.bus.inbound_size,
                "outbound_size": self.bus.outbound_size,
            },
            "jobs": job_counts,
        }

    async def apply_active_model_profile(self) -> None:
        if self.model_profile_service is None:
            return
        await self.apply_model_profile(_active_runtime_profile(self))

    async def apply_model_profile(self, profile: dict[str, object]) -> None:
        if self.runtime_profile_applier is None:
            return
        await self.runtime_profile_applier.apply(profile)


def _default_context_builder(options: RuntimeOptions) -> RuntimeContext:
    return build_runtime_context(options, load_session_state=False)


def _default_tts_service_builder(workspace: Path) -> TTSService:
    return build_default_tts_service(workspace)


def _default_asr_service_builder(workspace: Path) -> ASRService:
    return build_default_asr_service(workspace)


def _resolve_runtime_path(
    workspace: Path | None,
    path: str | Path,
) -> Path:
    resolved_path = Path(path).expanduser()
    if resolved_path.is_absolute() or workspace is None:
        return resolved_path
    return workspace / resolved_path


def _context_storage_root(context: RuntimeContext) -> Path:
    return context.storage_root or context.workspace / ".echobot"


def _build_runtime_model_services(
    model_profile_service: ModelProfileService,
) -> tuple[LLMModelService, VoiceModelService, Live2DModelService]:
    return (
        LLMModelService(LLMModelRepository(model_profile_service)),
        VoiceModelService(VoiceModelRepository(model_profile_service)),
        Live2DModelService(Live2DModelRepository(model_profile_service)),
    )


def _active_runtime_profile(runtime: object) -> dict[str, object]:
    llm_service = getattr(runtime, "llm_model_service", None)
    voice_service = getattr(runtime, "voice_model_service", None)
    live2d_service = getattr(runtime, "live2d_model_service", None)
    if llm_service is None or voice_service is None or live2d_service is None:
        model_profile_service = getattr(runtime, "model_profile_service", None)
        if model_profile_service is None:
            return {}
        return model_profile_service.active_profile_for_runtime()

    llm_profile = llm_service.active_runtime_profile()
    voice_profile = voice_service.active_runtime_profile()
    live2d_profile = live2d_service.active_runtime_profile()
    return {
        "profile_id": str(llm_profile.get("profile_id") or ""),
        "label": str(llm_profile.get("label") or ""),
        "chat": llm_profile.get("chat", {}),
        "tts": voice_profile.get("tts", {}),
        "asr": voice_profile.get("asr", {}),
        "live2d": live2d_profile.get("live2d", {}),
        "updated_at": str(llm_profile.get("updated_at") or ""),
    }


def _user_stage_scope_key(user_id: str) -> str:
    from .auth import user_storage_key

    return user_storage_key(user_id) if user_id else "default"


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
        self.stage_event_broker = parent.stage_event_broker
        self.session_runtime_override_service = SessionRuntimeOverrideService()
        self.tts_service: TTSService | None = None
        self.asr_service: ASRService | None = None
        self.channel_service: ChannelService | None = None
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
        self.chat_service = ChatService(
            self.context.coordinator,
            self.session_service,
        )
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
        ) = _build_runtime_model_services(self.model_profile_service)
        self.channel_service = self.parent.channel_service
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
        from .auth import TrustedUserConfig

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
            "workspace": str(self.context.workspace),
            "storage_root": str(self.storage_root),
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
        await self.apply_model_profile(_active_runtime_profile(self))

    async def apply_model_profile(self, profile: dict[str, object]) -> None:
        if self.runtime_profile_applier is None:
            return
        await self.runtime_profile_applier.apply(profile)

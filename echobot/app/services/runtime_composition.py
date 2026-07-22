from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...asr import ASRService
from ...channels import ChannelsConfig
from ...gateway import DeliveryStore, GatewaySessionService, RouteSessionStore
from ...runtime.bootstrap import RuntimeContext
from ...runtime.session_service import SessionLifecycleService
from ...tts import TTSService
from .character_profiles import CharacterProfileSettingsService
from .chat import ChatService
from .channels import ChannelService
from .live2d_models import Live2DModelService
from .llm_models import LLMModelService
from .model_profiles import ModelProfileService
from .roles import RoleService
from .runtime_model_services import build_runtime_model_services
from .runtime_profile_applier import RuntimeProfileApplier
from .voice_models import VoiceModelService
from .web_console import WebConsoleService


ChannelStatusGetter = Callable[[], dict[str, dict[str, bool]]]
ChannelReload = Callable[[ChannelsConfig | None], Awaitable[None]]


@dataclass(slots=True)
class RuntimeComposition:
    """The service graph shared by the process and user-scoped runtimes."""

    delivery_store: DeliveryStore
    route_session_store: RouteSessionStore
    session_service: GatewaySessionService
    chat_service: ChatService
    role_service: RoleService
    character_profile_settings_service: CharacterProfileSettingsService
    model_profile_service: ModelProfileService
    llm_model_service: LLMModelService
    voice_model_service: VoiceModelService
    live2d_model_service: Live2DModelService
    channel_service: ChannelService | None
    web_console_service: WebConsoleService
    runtime_profile_applier: RuntimeProfileApplier
    tts_service: TTSService
    asr_service: ASRService

    def install_on(self, runtime: Any) -> None:
        """Install common services while keeping runtime public attributes stable."""
        for name in (
            "delivery_store",
            "route_session_store",
            "session_service",
            "chat_service",
            "role_service",
            "character_profile_settings_service",
            "model_profile_service",
            "llm_model_service",
            "voice_model_service",
            "live2d_model_service",
            "channel_service",
            "web_console_service",
            "runtime_profile_applier",
            "tts_service",
            "asr_service",
        ):
            if name == "channel_service" and not hasattr(runtime, name):
                continue
            setattr(runtime, name, getattr(self, name))

    async def initialize_speech(self) -> None:
        initialized = await self.web_console_service.initialize_runtime_settings()
        if not initialized:
            await self.asr_service.on_startup()


def build_runtime_composition(
    *,
    context: RuntimeContext,
    storage_root: Path,
    tts_service: TTSService,
    asr_service: ASRService,
    model_profile_seed: ModelProfileService | None = None,
    character_profile_seed: CharacterProfileSettingsService | None = None,
    channel_config_path: str | Path | None = None,
    get_channel_status: ChannelStatusGetter | None = None,
    reload_channels: ChannelReload | None = None,
) -> RuntimeComposition:
    """Build the common runtime services for AppRuntime and user runtimes.

    A user runtime omits the channel arguments; the process runtime supplies
    them to retain its channel administration service.
    """
    delivery_store = DeliveryStore(storage_root / "delivery.json")
    route_session_store = RouteSessionStore(storage_root / "route_sessions.json")
    core_session_service = SessionLifecycleService(
        context.session_store,
        context.agent_session_store,
        coordinator=context.coordinator,
    )
    session_service = GatewaySessionService(
        core_session_service,
        route_session_store=route_session_store,
        delivery_store=delivery_store,
    )
    character_profile_settings_service = CharacterProfileSettingsService(storage_root)
    if character_profile_seed is not None:
        character_profile_settings_service.seed_from(character_profile_seed)

    model_profile_service = ModelProfileService(storage_root)
    if model_profile_seed is not None:
        model_profile_service.seed_from(model_profile_seed)

    llm_model_service, voice_model_service, live2d_model_service = (
        build_runtime_model_services(model_profile_service)
    )
    channel_service = None
    if channel_config_path is not None:
        if get_channel_status is None or reload_channels is None:
            raise ValueError(
                "channel status and reload callbacks are required with a channel path",
            )
        channel_service = ChannelService(
            config_path=channel_config_path,
            get_status=get_channel_status,
            reload_channels=reload_channels,
        )

    web_console_service = WebConsoleService(
        context.workspace,
        tts_service,
        asr_service,
        storage_root=storage_root,
    )
    return RuntimeComposition(
        delivery_store=delivery_store,
        route_session_store=route_session_store,
        session_service=session_service,
        chat_service=ChatService(context.coordinator),
        role_service=RoleService(context.role_registry, context.session_store),
        character_profile_settings_service=character_profile_settings_service,
        model_profile_service=model_profile_service,
        llm_model_service=llm_model_service,
        voice_model_service=voice_model_service,
        live2d_model_service=live2d_model_service,
        channel_service=channel_service,
        web_console_service=web_console_service,
        runtime_profile_applier=RuntimeProfileApplier(
            context=context,
            web_console_service=web_console_service,
        ),
        tts_service=tts_service,
        asr_service=asr_service,
    )

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from ..asr import (
    ASRService,
    OpenAITranscriptionsASRProvider,
    build_default_asr_service,
)
from ..asr.factory import DEFAULT_ASR_PROVIDER
from ..channels import (
    ChannelManager,
    ChannelsConfig,
    MessageBus,
    OutboundMessage,
    load_channels_config,
)
from ..gateway import (
    DeliveryStore,
    GatewayRuntime,
    GatewaySessionService,
    RouteSessionStore,
)
from ..runtime.bootstrap import RuntimeContext, RuntimeOptions, build_runtime_context
from ..runtime.session_service import SessionLifecycleService
from ..models import message_content_to_text
from ..providers.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAICompatibleSettings,
)
from ..tts import TTSService, build_default_tts_service
from ..tts.factory import DEFAULT_TTS_PROVIDER
from ..tts.providers.openai_compatible import (
    DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
    DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE,
    OpenAICompatibleTTSProvider,
)
from .auth import user_storage_root
from .services.chat import ChatService
from .services.character_profiles import CharacterProfileSettingsService
from .services.channels import ChannelService
from .services.model_profiles import ModelProfileService
from .services.roles import RoleService
from .services.stage_events import StageEventBroker, StageEventPublishRequest
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
        self.channels_config: ChannelsConfig | None = None
        self.channel_manager: ChannelManager | None = None
        self.delivery_store: DeliveryStore | None = None
        self.route_session_store: RouteSessionStore | None = None
        self.gateway: GatewayRuntime | None = None
        self.gateway_task: asyncio.Task[None] | None = None
        self.session_service: GatewaySessionService | None = None
        self.chat_service: ChatService | None = None
        self.role_service: RoleService | None = None
        self.character_profile_settings_service: CharacterProfileSettingsService | None = None
        self.model_profile_service: ModelProfileService | None = None
        self.channel_service: ChannelService | None = None
        self.stage_event_broker = StageEventBroker()
        self.web_console_service: WebConsoleService | None = None
        self.tts_service: TTSService | None = None
        self.asr_service: ASRService | None = None
        self._user_runtimes: dict[str, UserScopedRuntime] = {}
        self._user_runtime_lock = asyncio.Lock()
        self._started = False

    @property
    def workspace(self) -> Path:
        if self.context is None:
            raise RuntimeError("App runtime has not been started")
        return self.context.workspace

    async def start(self) -> None:
        if self._started:
            return

        self.context = self._context_builder(self.runtime_options)
        self.bus = MessageBus()
        self.channels_config = load_channels_config(self.channel_config_path)
        self.channel_manager = ChannelManager(
            self.channels_config,
            self.bus,
            attachment_store=self.context.attachment_store,
        )
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
        asr_initialized = await self.web_console_service.initialize_runtime_settings()
        if not asr_initialized:
            await self.asr_service.on_startup()
        await self.apply_active_model_profile()

        await self.channel_manager.start_all()
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

        if self.channel_manager is not None:
            await self.channel_manager.stop_all()

        for runtime in list(self._user_runtimes.values()):
            await runtime.stop()
        self._user_runtimes.clear()
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

        storage_root = user_storage_root(self.context.workspace, user_id)
        cache_key = str(storage_root)
        runtime = self._user_runtimes.get(cache_key)
        if runtime is not None:
            return runtime

        async with self._user_runtime_lock:
            runtime = self._user_runtimes.get(cache_key)
            if runtime is not None:
                return runtime

            runtime = UserScopedRuntime(
                parent=self,
                user_id=user_id,
                storage_root=storage_root,
            )
            await runtime.start()
            self._user_runtimes[cache_key] = runtime
            return runtime

    async def reload_channels(
        self,
        config: ChannelsConfig | None = None,
    ) -> None:
        if self.bus is None:
            raise RuntimeError("App runtime has not been started")

        next_config = config or load_channels_config(self.channel_config_path)
        next_manager = ChannelManager(
            next_config,
            self.bus,
            attachment_store=self.context.attachment_store,
        )
        await next_manager.start_all()

        previous_manager = self.channel_manager
        self.channel_manager = next_manager
        self.channels_config = next_config

        if previous_manager is not None:
            await previous_manager.stop_all()

    def channel_status(self) -> dict[str, dict[str, bool]]:
        if self.channel_manager is None:
            return {}
        return self.channel_manager.get_status()

    async def publish_gateway_stage_event(
        self,
        session_name: str,
        outbound: OutboundMessage,
    ) -> None:
        if self.channels_config is None:
            return
        channel_config = self.channels_config.get(outbound.address.channel)
        if not bool(getattr(channel_config, "mirror_to_stage", False)):
            return

        stage_session_name = (
            str(getattr(channel_config, "stage_session_name", "") or "").strip()
            or session_name
        )
        text = message_content_to_text(outbound.content or outbound.text).strip()
        if not text:
            return

        await self.stage_event_broker.publish(
            scope_key="default",
            request=StageEventPublishRequest(
                kind="assistant_final",
                session_name=stage_session_name,
                text=text,
                speaker="Echo",
                source=outbound.address.channel,
                metadata={
                    "gateway_channel": outbound.address.channel,
                    "gateway_session_name": session_name,
                },
            ),
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
        await self.apply_model_profile(
            self.model_profile_service.active_profile_for_runtime(),
        )

    async def apply_model_profile(self, profile: dict[str, object]) -> None:
        if self.context is None:
            return

        chat = profile.get("chat") if isinstance(profile, dict) else None
        if isinstance(chat, dict):
            self._apply_chat_model_profile(chat)

        tts = profile.get("tts") if isinstance(profile, dict) else None
        if isinstance(tts, dict) and self.web_console_service is not None:
            try:
                await _apply_tts_model_profile(self.web_console_service, tts)
            except (ValueError, RuntimeError):
                pass

        asr = profile.get("asr") if isinstance(profile, dict) else None
        if isinstance(asr, dict) and self.web_console_service is not None:
            try:
                await _apply_asr_model_profile(self.web_console_service, asr)
            except (ValueError, RuntimeError):
                pass

    def _apply_chat_model_profile(self, chat: dict[str, object]) -> None:
        if self.context is None:
            return
        _apply_chat_model_profile_to_context(self.context, chat)


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


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _profile_extra_body() -> dict[str, object]:
    raw_value = os.environ.get("LLM_EXTRA_BODY", "").strip()
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_env_object(name: str) -> dict[str, object]:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _csv_env(name: str) -> list[str]:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return []
    return [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]


def _profile_text(
    section: dict[str, object],
    key: str,
    env_name: str,
    default: str = "",
) -> str:
    return (
        str(section.get(key) or "").strip()
        or os.environ.get(env_name, "").strip()
        or default
    )


async def _apply_tts_model_profile(
    web_console_service: WebConsoleService,
    tts: dict[str, object],
) -> None:
    tts_service = web_console_service.tts_service
    provider_name = (
        str(tts.get("provider") or "").strip()
        or os.environ.get("ECHOBOT_TTS_PROVIDER", "").strip()
        or DEFAULT_TTS_PROVIDER
    )
    if provider_name == "openai-compatible":
        provider = OpenAICompatibleTTSProvider(
            api_key=_profile_text(tts, "api_key", "ECHOBOT_TTS_OPENAI_API_KEY", "EMPTY"),
            model=_profile_text(tts, "model", "ECHOBOT_TTS_OPENAI_MODEL"),
            base_url=_profile_text(
                tts,
                "base_url",
                "ECHOBOT_TTS_OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            ),
            timeout=max(1.0, _float_env("ECHOBOT_TTS_OPENAI_TIMEOUT", 60.0)),
            default_voice=_profile_text(
                tts,
                "voice",
                "ECHOBOT_TTS_OPENAI_DEFAULT_VOICE",
                DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE,
            ),
            response_format=os.environ.get(
                "ECHOBOT_TTS_OPENAI_RESPONSE_FORMAT",
                DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
            ).strip() or DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
            voices=_csv_env("ECHOBOT_TTS_OPENAI_VOICES"),
            instructions=os.environ.get("ECHOBOT_TTS_OPENAI_INSTRUCTIONS", "").strip(),
            extra_body=_json_env_object("ECHOBOT_TTS_OPENAI_EXTRA_BODY"),
        )
        await tts_service.replace_provider(
            "openai-compatible",
            provider,
            set_default=True,
        )
        return

    tts_service.set_default_provider(provider_name)


async def _apply_asr_model_profile(
    web_console_service: WebConsoleService,
    asr: dict[str, object],
) -> None:
    asr_service = web_console_service.asr_service
    provider_name = (
        str(asr.get("provider") or "").strip()
        or os.environ.get("ECHOBOT_ASR_PROVIDER", "").strip()
        or DEFAULT_ASR_PROVIDER
    )
    if provider_name == "openai-transcriptions":
        provider = OpenAITranscriptionsASRProvider(
            sample_rate=asr_service.sample_rate,
            api_key=_profile_text(asr, "api_key", "ECHOBOT_ASR_OPENAI_API_KEY", "EMPTY"),
            model=_profile_text(asr, "model", "ECHOBOT_ASR_OPENAI_MODEL"),
            base_url=_profile_text(
                asr,
                "base_url",
                "ECHOBOT_ASR_OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            ),
            timeout=max(1.0, _float_env("ECHOBOT_ASR_OPENAI_TIMEOUT", 60.0)),
            language=_profile_text(asr, "language", "ECHOBOT_ASR_OPENAI_LANGUAGE"),
            prompt=os.environ.get("ECHOBOT_ASR_OPENAI_PROMPT", "").strip(),
            temperature=_optional_float(
                os.environ.get("ECHOBOT_ASR_OPENAI_TEMPERATURE", ""),
            ),
        )
        await asr_service.replace_asr_provider(
            "openai-transcriptions",
            provider,
        )

    await web_console_service.set_selected_asr_provider(provider_name)


def _apply_chat_model_profile_to_context(
    context: RuntimeContext,
    chat: dict[str, object],
) -> None:
    model = (
        str(chat.get("model") or "").strip()
        or os.environ.get("LLM_MODEL", "").strip()
    )
    if not model:
        return
    base_url = (
        str(chat.get("base_url") or "").strip()
        or os.environ.get("LLM_BASE_URL", "").strip()
        or "https://api.openai.com/v1"
    )
    provider = OpenAICompatibleProvider(
        OpenAICompatibleSettings(
            api_key=_profile_text(chat, "api_key", "LLM_API_KEY", "EMPTY"),
            model=model,
            base_url=base_url,
            timeout=_float_env("LLM_TIMEOUT", 60.0),
            extra_body=_profile_extra_body(),
        ),
        attachment_store=context.attachment_store,
    )
    context.agent.provider = provider
    context.coordinator.set_llm_provider(provider)
    context.coordinator.set_generation_defaults(
        temperature=_optional_float(chat.get("temperature")),
        max_tokens=_optional_int(chat.get("max_tokens")),
    )


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
        self.web_console_service: WebConsoleService | None = None
        self.stage_event_broker = parent.stage_event_broker
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
        self.channel_service = self.parent.channel_service
        self.asr_service = self.parent._asr_service_builder(self.context.workspace)
        self.tts_service = self.parent._tts_service_builder(self.context.workspace)
        self.web_console_service = WebConsoleService(
            self.context.workspace,
            self.tts_service,
            self.asr_service,
            storage_root=self.storage_root,
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
        await self.parent.publish_gateway_stage_event(session_name, outbound)

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
        await self.apply_model_profile(
            self.model_profile_service.active_profile_for_runtime(),
        )

    async def apply_model_profile(self, profile: dict[str, object]) -> None:
        if self.context is None:
            return

        chat = profile.get("chat") if isinstance(profile, dict) else None
        if isinstance(chat, dict):
            self._apply_chat_model_profile(chat)

        tts = profile.get("tts") if isinstance(profile, dict) else None
        if isinstance(tts, dict) and self.web_console_service is not None:
            try:
                await _apply_tts_model_profile(self.web_console_service, tts)
            except (ValueError, RuntimeError):
                pass

        asr = profile.get("asr") if isinstance(profile, dict) else None
        if isinstance(asr, dict) and self.web_console_service is not None:
            try:
                await _apply_asr_model_profile(self.web_console_service, asr)
            except (ValueError, RuntimeError):
                pass

    def _apply_chat_model_profile(self, chat: dict[str, object]) -> None:
        if self.context is None:
            return
        _apply_chat_model_profile_to_context(self.context, chat)

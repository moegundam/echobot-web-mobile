from __future__ import annotations

import asyncio
import inspect
import logging
from copy import deepcopy
from collections.abc import Callable
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
from ..concurrency import AsyncReentrantLock
from ..gateway import (
    DeliveryStore,
    GatewayRuntime,
    GatewaySessionService,
    RouteSessionStore,
)
from ..runtime.bootstrap import RuntimeContext, RuntimeOptions, build_runtime_context
from ..tts import TTSService, build_default_tts_service
from .services.chat import ChatService
from .services.channel_runtime_manager import ChannelRuntimeManager
from .services.character_profiles import CharacterProfileSettingsService
from .services.channels import ChannelService
from .services.live2d_models import Live2DModelService
from .services.llm_models import LLMModelService
from .services.model_profiles import ModelProfileService
from .services.roles import RoleService
from .services.runtime_composition import build_runtime_composition
from .services.runtime_context_events import notify_session_runtime_context_changed
from .services.runtime_model_services import active_runtime_profile
from .services.runtime_profile_applier import RuntimeProfileApplier
from .services.session_runtime_overrides import SessionRuntimeOverrideService
from .services.session_turn_runtime import resolve_session_turn_runtime
from .services.stage_event_publisher import StageEventPublisher
from .services.stage_event_broker_factory import create_stage_event_broker
from .services.user_runtime_factory import UserRuntimeFactory
from .services.user_scoped_runtime import UserScopedRuntime
from .services.voice_models import VoiceModelService
from .services.web_console import WebConsoleService


RuntimeContextBuilder = Callable[[RuntimeOptions], RuntimeContext]
TTSServiceBuilder = Callable[[Path], TTSService]
ASRServiceBuilder = Callable[[Path], ASRService]
logger = logging.getLogger(__name__)


class AppRuntimeStopError(RuntimeError):
    """Reports shutdown failures after every owned resource was attempted."""

    def __init__(self, failures: list[tuple[str, Exception]]) -> None:
        self.failures = tuple(failures)
        details = "; ".join(
            f"{name}: {type(error).__name__}: {error}"
            for name, error in failures
        )
        super().__init__(f"App runtime cleanup failed: {details}")


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
        self.stage_event_broker = create_stage_event_broker()
        self.stage_event_publisher = StageEventPublisher(self.stage_event_broker)
        self.session_binding_lock = asyncio.Lock()
        self.session_runtime_override_service = SessionRuntimeOverrideService()
        self.web_console_service: WebConsoleService | None = None
        self.runtime_profile_applier: RuntimeProfileApplier | None = None
        self.last_applied_model_profile: dict[str, object] = {}
        self.model_profile_lock = AsyncReentrantLock()
        self.model_profile_revision = 0
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

        try:
            await self._start_resources()
        except BaseException:
            # ``stop`` normally ignores an unstarted runtime. Mark this partial
            # graph as owned so every resource created before the failure is
            # attempted exactly once.
            self._started = True
            try:
                await self.stop()
            except Exception:
                logger.exception("Failed to fully roll back EchoBot app startup")
            raise

    async def _start_resources(self) -> None:

        self.context = self._context_builder(self.runtime_options)
        self.bus = MessageBus()
        self.channel_runtime_manager = ChannelRuntimeManager(
            config_path=self.channel_config_path,
            bus=self.bus,
            attachment_store=self.context.attachment_store,
        )
        await self.channel_runtime_manager.start()
        self.asr_service = self._asr_service_builder(self.context.workspace)
        self.tts_service = self._tts_service_builder(self.context.workspace)
        composition = build_runtime_composition(
            context=self.context,
            storage_root=_context_storage_root(self.context),
            tts_service=self.tts_service,
            asr_service=self.asr_service,
            channel_config_path=self.channel_config_path,
            get_channel_status=self.channel_status,
            reload_channels=self.reload_channels,
        )
        composition.install_on(self)
        self.gateway = GatewayRuntime(
            self.context,
            self.bus,
            session_service=self.session_service,
            runtime_for_user=self.for_user,
            stage_event_publisher=self.publish_gateway_stage_event,
            runtime_context_change_notifier=self.notify_session_runtime_context_changed,
        )
        self.context.coordinator.set_turn_runtime_resolver(
            lambda session_name, role_name: resolve_session_turn_runtime(
                self,
                session_name,
                role_name,
            )
        )
        await composition.initialize_speech()
        await self.apply_active_model_profile()

        self.gateway_task = asyncio.create_task(
            self.gateway.run(),
            name="echobot_gateway_runtime",
        )
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return

        failures: list[tuple[str, Exception]] = []
        if self.gateway_task is not None:
            self.gateway_task.cancel()
            results = await asyncio.gather(self.gateway_task, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    failures.append(("gateway", result))
            self.gateway_task = None

        if self.channel_runtime_manager is not None:
            await _attempt_cleanup(
                failures,
                "channels",
                self.channel_runtime_manager.stop,
            )

        await _attempt_cleanup(
            failures,
            "user runtimes",
            self.user_runtime_factory.stop_all,
        )
        if self.context is not None:
            await _attempt_cleanup(
                failures,
                "coordinator",
                self.context.coordinator.close,
            )
            memory_support = getattr(self.context, "memory_support", None)
            if memory_support is not None:
                await _attempt_cleanup(
                    failures,
                    "memory",
                    memory_support.close,
                )
        if self.tts_service is not None:
            await _attempt_cleanup(failures, "tts", self.tts_service.close)
        if self.asr_service is not None:
            await _attempt_cleanup(failures, "asr", self.asr_service.close)
        if self.context is not None:
            close_session_stores = getattr(self.context, "close_session_stores", None)
            if callable(close_session_stores):
                await _attempt_cleanup(
                    failures,
                    "session repositories",
                    close_session_stores,
                )
        close_stage_broker = getattr(self.stage_event_broker, "close", None)
        if callable(close_stage_broker):
            await _attempt_cleanup(
                failures,
                "stage event broker",
                close_stage_broker,
            )

        self._started = False
        if failures:
            raise AppRuntimeStopError(failures)

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
            "workspace_name": self.context.workspace.name,
            "current_session": current_session.name,
            "current_role": current_role,
            "channels": self.channel_status(),
            "bus": {
                "inbound_size": self.bus.inbound_size,
                "outbound_size": self.bus.outbound_size,
            },
            "jobs": job_counts,
        }

    async def readiness_snapshot(self) -> dict[str, str]:
        if not self._started or self.gateway_task is None or self.gateway_task.done():
            raise RuntimeError("App runtime is not ready")
        await self.health_snapshot()
        return {"status": "ok"}

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


async def _attempt_cleanup(
    failures: list[tuple[str, Exception]],
    name: str,
    cleanup: Callable[[], object],
) -> None:
    try:
        result = cleanup()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        failures.append((name, exc))


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

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..attachments import AttachmentStore, DEFAULT_FILE_BUDGET, FileBudget
from ..agent import AgentCore
from ..config import configure_runtime_logging, load_env_file
from ..images import DEFAULT_IMAGE_BUDGET, ImageBudget
from ..memory import ReMeLightSettings, ReMeLightSupport
from ..orchestration import (
    ConversationCoordinator,
    ConversationJobStore,
    DecisionEngine,
    RoleCardRegistry,
    RoleplayEngine,
)
from ..providers.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAICompatibleSettings,
)
from ..providers.base import LLMProvider
from ..runtime.session_runner import SessionAgentRunner
from ..runtime.agent_traces import AgentTraceStore
from ..runtime.settings import (
    DEFAULT_SHELL_SAFETY_MODE,
    RuntimeConfigSnapshot,
    RuntimeControls,
    RuntimeSettings,
    RuntimeSettingsStore,
)
from ..runtime.session_repository import SessionRepository
from ..runtime.sessions import ChatSession, SessionStore
from ..runtime.sqlite_sessions import SQLiteSessionStore
from ..runtime.system_prompt import build_default_system_prompt
from ..scheduling.cron import CronService
from ..scheduling.heartbeat import HeartbeatService
from ..skill_support import SkillRegistry
from ..tools import ToolRegistry, create_basic_tool_registry


ToolRegistryFactory = Callable[[str, bool], ToolRegistry | None]


@dataclass(slots=True)
class RuntimeOptions:
    env_file: str = ".env"
    workspace: Path | None = None
    storage_root: Path | None = None
    tool_workspace: Path | None = None
    memory_workspace: Path | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    allow_unconfigured_llm: bool = False
    delegated_ack_enabled: bool | None = None
    no_tools: bool = False
    no_skills: bool = False
    no_memory: bool = False
    no_heartbeat: bool = False
    heartbeat_interval: int | None = None
    session: str | None = None
    new_session: str | None = None
    session_store_backend: str = "jsonl"
    agent_session_store_backend: str | None = None


@dataclass(slots=True)
class RuntimeContext:
    workspace: Path
    attachment_store: AttachmentStore
    supports_image_input: bool
    agent: AgentCore
    session_store: SessionRepository
    agent_session_store: SessionRepository
    session: ChatSession | None
    tool_registry: ToolRegistry | None
    skill_registry: SkillRegistry | None
    cron_service: CronService
    heartbeat_service: HeartbeatService | None
    session_runner: SessionAgentRunner
    coordinator: ConversationCoordinator
    role_registry: RoleCardRegistry
    memory_support: ReMeLightSupport | None
    heartbeat_file_path: Path
    heartbeat_interval_seconds: int
    tool_registry_factory: ToolRegistryFactory
    runtime_controls: RuntimeControls
    default_runtime_config: RuntimeConfigSnapshot
    storage_root: Path | None = None
    tool_workspace: Path | None = None
    decision_provider: LLMProvider | None = None
    roleplay_provider: LLMProvider | None = None
    dedicated_decision_provider: bool = False
    dedicated_roleplay_provider: bool = False
    default_temperature: float | None = None
    default_max_tokens: int | None = None

    def close_session_stores(self) -> None:
        """Close optional resource-backed repositories without widening the protocol."""
        close_session_repositories(self.session_store, self.agent_session_store)


def build_runtime_context(
    options: RuntimeOptions,
    *,
    load_session_state: bool,
) -> RuntimeContext:
    session_backend = _resolve_session_store_backend(options.session_store_backend)
    agent_session_backend = _resolve_session_store_backend(
        options.agent_session_store_backend or session_backend,
    )
    workspace = (options.workspace or Path(".")).resolve()
    storage_root = _storage_root(workspace, options.storage_root)
    tool_workspace = _resolve_optional_workspace(workspace, options.tool_workspace)
    tool_workspace.mkdir(parents=True, exist_ok=True)
    env_file_path = _resolve_runtime_path(workspace, options.env_file)
    load_env_file(str(env_file_path))
    default_runtime_config = _default_runtime_config(options)
    settings_store = RuntimeSettingsStore(_runtime_settings_path(storage_root))
    runtime_settings = settings_store.load()
    runtime_controls = RuntimeControls(
        shell_safety_mode=(
            runtime_settings.shell_safety_mode
            if runtime_settings.shell_safety_mode is not None
            else default_runtime_config.shell_safety_mode
        ),
        file_write_enabled=(
            runtime_settings.file_write_enabled
            if runtime_settings.file_write_enabled is not None
            else default_runtime_config.file_write_enabled
        ),
        cron_mutation_enabled=(
            runtime_settings.cron_mutation_enabled
            if runtime_settings.cron_mutation_enabled is not None
            else default_runtime_config.cron_mutation_enabled
        ),
        web_private_network_enabled=(
            runtime_settings.web_private_network_enabled
            if runtime_settings.web_private_network_enabled is not None
            else default_runtime_config.web_private_network_enabled
        ),
    )
    configure_runtime_logging()
    lightweight_max_tokens = _env_int("ECHOBOT_LIGHTWEIGHT_MAX_TOKENS", 4096)
    agent_max_steps = _env_int("ECHOBOT_AGENT_MAX_STEPS", 50)
    settings = OpenAICompatibleSettings.from_env(
        allow_unconfigured=options.allow_unconfigured_llm,
    )
    supports_image_input = _env_bool("ECHOBOT_LLM_SUPPORTS_IMAGE_INPUT", True)
    attachment_store = AttachmentStore(
        storage_root / "attachments",
        image_budget=_image_budget_from_env(),
        file_budget=_file_budget_from_env(),
    )
    dedicated_decision_provider = _has_provider_env("DECIDER_LLM_")
    dedicated_roleplay_provider = _has_provider_env("ROLE_LLM_")
    decider_provider = _build_provider_from_env(
        prefix="DECIDER_LLM_",
        fallback_settings=settings,
        attachment_store=attachment_store,
    )
    role_provider = _build_provider_from_env(
        prefix="ROLE_LLM_",
        fallback_settings=settings,
        attachment_store=attachment_store,
    )

    memory_support = None
    if not options.no_memory and ReMeLightSupport.is_available():
        memory_settings = ReMeLightSettings.from_provider_settings(
            workspace,
            settings,
        )
        if options.memory_workspace is not None:
            memory_settings.working_dir = _resolve_optional_workspace(
                workspace,
                options.memory_workspace,
            )
        memory_support = ReMeLightSupport(memory_settings)

    provider = OpenAICompatibleProvider(
        settings,
        attachment_store=attachment_store,
    )
    cron_store_path = storage_root / "cron" / "jobs.json"
    heartbeat_file_path = _heartbeat_file_path(workspace, storage_root)
    heartbeat_interval_seconds = _heartbeat_interval_seconds(options)
    agent = AgentCore(
        provider,
        system_prompt=_build_system_prompt_provider(
            workspace=tool_workspace,
            supports_image_input=supports_image_input,
            memory_support=memory_support,
            cron_store_path=cron_store_path,
            heartbeat_file_path=heartbeat_file_path,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            runtime_controls=runtime_controls,
        ),
        memory_support=memory_support,
    )
    session_store = _build_session_store(
        storage_root,
        namespace="sessions",
        backend=session_backend,
    )
    agent_session_store = _build_session_store(
        storage_root,
        namespace="agent_sessions",
        backend=agent_session_backend,
    )
    agent_trace_store = AgentTraceStore(storage_root / "agent_traces")
    session = _load_session(session_store, options) if load_session_state else None
    cron_service = CronService(cron_store_path)
    tool_registry_factory = _build_tool_registry_factory(
        options,
        workspace=tool_workspace,
        attachment_store=attachment_store,
        supports_image_input=supports_image_input,
        memory_support=memory_support,
        cron_service=cron_service,
        runtime_controls=runtime_controls,
    )
    tool_registry = None
    if session is not None:
        tool_registry = tool_registry_factory(session.name, False)
    skill_registry = None if options.no_skills else SkillRegistry.discover()
    session_runner = SessionAgentRunner(
        agent,
        agent_session_store,
        skill_registry=skill_registry,
        tool_registry_factory=tool_registry_factory,
        default_temperature=options.temperature,
        default_max_tokens=options.max_tokens,
        default_max_steps=agent_max_steps,
        trace_store=agent_trace_store,
    )
    role_registry = RoleCardRegistry.discover(project_root=workspace)
    job_store = ConversationJobStore(storage_root / "jobs" / "jobs.json")
    decision_engine = DecisionEngine(
        AgentCore(decider_provider),
        max_tokens=lightweight_max_tokens,
    )
    roleplay_engine = RoleplayEngine(
        AgentCore(role_provider),
        role_registry,
        default_temperature=options.temperature,
        default_max_tokens=options.max_tokens,
        lightweight_max_tokens=lightweight_max_tokens,
    )
    coordinator = ConversationCoordinator(
        session_store=session_store,
        agent_runner=session_runner,
        decision_engine=decision_engine,
        roleplay_engine=roleplay_engine,
        role_registry=role_registry,
        delegated_ack_enabled=(
            runtime_settings.delegated_ack_enabled
            if runtime_settings.delegated_ack_enabled is not None
            else default_runtime_config.delegated_ack_enabled
        ),
        job_store=job_store,
    )
    heartbeat_service = None
    if not options.no_heartbeat and _heartbeat_enabled():
        heartbeat_service = HeartbeatService(
            heartbeat_file=heartbeat_file_path,
            provider=provider,
            interval_seconds=heartbeat_interval_seconds,
            enabled=True,
        )

    return RuntimeContext(
        workspace=workspace,
        attachment_store=attachment_store,
        supports_image_input=supports_image_input,
        agent=agent,
        session_store=session_store,
        agent_session_store=agent_session_store,
        session=session,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
        session_runner=session_runner,
        coordinator=coordinator,
        role_registry=role_registry,
        memory_support=memory_support,
        heartbeat_file_path=heartbeat_file_path,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        tool_registry_factory=tool_registry_factory,
        runtime_controls=runtime_controls,
        default_runtime_config=default_runtime_config,
        storage_root=storage_root,
        tool_workspace=tool_workspace,
        decision_provider=decider_provider,
        roleplay_provider=role_provider,
        dedicated_decision_provider=dedicated_decision_provider,
        dedicated_roleplay_provider=dedicated_roleplay_provider,
        default_temperature=options.temperature,
        default_max_tokens=options.max_tokens,
    )


def _build_tool_registry_factory(
    options: RuntimeOptions,
    *,
    workspace: Path,
    attachment_store: AttachmentStore,
    supports_image_input: bool,
    memory_support: ReMeLightSupport | None,
    cron_service: CronService,
    runtime_controls: RuntimeControls,
) -> ToolRegistryFactory:
    def factory(session_name: str, scheduled_context: bool) -> ToolRegistry | None:
        if options.no_tools:
            return None
        return create_basic_tool_registry(
            workspace,
            attachment_store=attachment_store,
            supports_image_input=supports_image_input,
            memory_support=memory_support,
            cron_service=cron_service,
            session_name=session_name,
            allow_file_writes=runtime_controls.file_write_enabled,
            allow_cron_mutations=(
                runtime_controls.cron_mutation_enabled and not scheduled_context
            ),
            allow_private_network=runtime_controls.web_private_network_enabled,
            shell_safety_mode=runtime_controls.shell_safety_mode,
        )

    return factory


def _build_system_prompt_provider(
    *,
    workspace: Path,
    supports_image_input: bool,
    memory_support: ReMeLightSupport | None,
    cron_store_path: Path,
    heartbeat_file_path: Path,
    heartbeat_interval_seconds: int,
    runtime_controls: RuntimeControls,
):
    def provider() -> str:
        return build_default_system_prompt(
            workspace,
            supports_image_input=supports_image_input,
            enable_project_memory=memory_support is not None,
            memory_workspace=(
                memory_support.working_dir
                if memory_support is not None
                else None
            ),
            enable_scheduling=True,
            cron_store_path=cron_store_path,
            heartbeat_file_path=heartbeat_file_path,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            shell_safety_mode=runtime_controls.shell_safety_mode,
            file_write_enabled=runtime_controls.file_write_enabled,
            cron_mutation_enabled=runtime_controls.cron_mutation_enabled,
            web_private_network_enabled=runtime_controls.web_private_network_enabled,
        )

    return provider


def _load_session(
    session_store: SessionRepository,
    options: RuntimeOptions,
) -> ChatSession:
    if options.new_session:
        return session_store.create_session(options.new_session)

    if options.session:
        session = session_store.load_or_create_session(options.session)
        session_store.set_current_session(session.name)
        return session

    return session_store.load_current_session()


def _resolve_session_store_backend(value: str) -> str:
    backend = str(value or "").strip().lower()
    if backend not in {"jsonl", "sqlite"}:
        raise ValueError(
            "session store backend must be one of: jsonl, sqlite",
        )
    return backend


def _build_session_store(
    storage_root: Path,
    *,
    namespace: str,
    backend: str,
) -> SessionRepository:
    if backend == "jsonl":
        return SessionStore(storage_root / namespace)
    if backend == "sqlite":
        return SQLiteSessionStore(storage_root / f"{namespace}.sqlite3")
    raise ValueError(f"Unsupported session store backend: {backend}")


def close_session_repositories(*repositories: SessionRepository) -> None:
    """Close repositories that own external resources; JSONL remains a no-op."""
    failures: list[Exception] = []
    for repository in repositories:
        close = getattr(repository, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                failures.append(exc)
    if failures:
        details = "; ".join(
            f"{type(error).__name__}: {error}" for error in failures
        )
        raise RuntimeError(f"Session repository cleanup failed: {details}") from failures[0]


def _heartbeat_file_path(workspace: Path, storage_root: Path) -> Path:
    file_name = os.environ.get(
        "ECHOBOT_HEARTBEAT_FILE",
        ".echobot/HEARTBEAT.md",
    )
    if file_name == ".echobot/HEARTBEAT.md":
        return storage_root / "HEARTBEAT.md"
    return workspace / file_name


def _heartbeat_interval_seconds(options: RuntimeOptions) -> int:
    if options.heartbeat_interval is not None:
        return max(int(options.heartbeat_interval), 1)
    raw_value = os.environ.get("ECHOBOT_HEARTBEAT_INTERVAL_SECONDS", "1800")
    try:
        value = int(raw_value)
    except ValueError:
        value = 1800
    return max(value, 1)


def _heartbeat_enabled() -> bool:
    raw_value = os.environ.get("ECHOBOT_HEARTBEAT_ENABLED", "true").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _delegated_ack_enabled(
    options: RuntimeOptions,
    *,
    runtime_settings,
) -> bool:
    if options.delegated_ack_enabled is not None:
        return bool(options.delegated_ack_enabled)
    if runtime_settings.delegated_ack_enabled is not None:
        return bool(runtime_settings.delegated_ack_enabled)
    return _env_bool("ECHOBOT_DELEGATED_ACK_ENABLED", True)


def _shell_safety_mode(runtime_settings) -> str:
    if runtime_settings.shell_safety_mode is not None:
        return runtime_settings.shell_safety_mode

    raw_value = os.environ.get("ECHOBOT_SHELL_SAFETY_MODE", "").strip().lower()
    if raw_value:
        return raw_value
    return DEFAULT_SHELL_SAFETY_MODE


def _file_write_enabled(runtime_settings) -> bool:
    if runtime_settings.file_write_enabled is not None:
        return bool(runtime_settings.file_write_enabled)
    return _env_bool("ECHOBOT_FILE_WRITE_ENABLED", True)


def _cron_mutation_enabled(runtime_settings) -> bool:
    if runtime_settings.cron_mutation_enabled is not None:
        return bool(runtime_settings.cron_mutation_enabled)
    return _env_bool("ECHOBOT_CRON_MUTATION_ENABLED", True)


def _web_private_network_enabled(runtime_settings) -> bool:
    if runtime_settings.web_private_network_enabled is not None:
        return bool(runtime_settings.web_private_network_enabled)
    return _env_bool("ECHOBOT_WEB_PRIVATE_NETWORK_ENABLED", False)


def _default_runtime_config(options: RuntimeOptions) -> RuntimeConfigSnapshot:
    runtime_settings = RuntimeSettings()
    return RuntimeConfigSnapshot(
        delegated_ack_enabled=_delegated_ack_enabled(
            options,
            runtime_settings=runtime_settings,
        ),
        shell_safety_mode=_shell_safety_mode(runtime_settings),
        file_write_enabled=_file_write_enabled(runtime_settings),
        cron_mutation_enabled=_cron_mutation_enabled(runtime_settings),
        web_private_network_enabled=_web_private_network_enabled(runtime_settings),
    )


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        return max(int(raw_value), 1)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    cleaned = raw_value.strip().lower()
    if not cleaned:
        return default
    return cleaned not in {"0", "false", "no", "off"}


def _image_budget_from_env() -> ImageBudget:
    defaults = DEFAULT_IMAGE_BUDGET
    return ImageBudget(
        max_input_bytes=_env_int(
            "ECHOBOT_IMAGE_MAX_INPUT_BYTES",
            defaults.max_input_bytes,
        ),
        max_output_bytes=_env_int(
            "ECHOBOT_IMAGE_MAX_OUTPUT_BYTES",
            defaults.max_output_bytes,
        ),
        max_side=_env_int(
            "ECHOBOT_IMAGE_MAX_SIDE",
            defaults.max_side,
        ),
        max_pixels=_env_int(
            "ECHOBOT_IMAGE_MAX_PIXELS",
            defaults.max_pixels,
        ),
        start_quality=defaults.start_quality,
        min_quality=defaults.min_quality,
        quality_step=defaults.quality_step,
        resize_step=defaults.resize_step,
        max_resize_attempts=defaults.max_resize_attempts,
    )


def _file_budget_from_env() -> FileBudget:
    defaults = DEFAULT_FILE_BUDGET
    return FileBudget(
        max_input_bytes=_env_int(
            "ECHOBOT_FILE_MAX_INPUT_BYTES",
            defaults.max_input_bytes,
        ),
    )


def _resolve_runtime_path(workspace: Path, path: str | Path) -> Path:
    resolved_path = Path(path).expanduser()
    if resolved_path.is_absolute():
        return resolved_path
    return workspace / resolved_path


def _runtime_settings_path(storage_root: Path) -> Path:
    return storage_root / "runtime_settings.json"


def _storage_root(workspace: Path, storage_root: str | Path | None) -> Path:
    if storage_root is None:
        return workspace / ".echobot"
    resolved_root = Path(storage_root).expanduser()
    if resolved_root.is_absolute():
        return resolved_root.resolve()
    return (workspace / resolved_root).resolve()


def _resolve_optional_workspace(
    project_workspace: Path,
    configured_workspace: str | Path | None,
) -> Path:
    if configured_workspace is None:
        return project_workspace
    resolved_workspace = Path(configured_workspace).expanduser()
    if resolved_workspace.is_absolute():
        return resolved_workspace.resolve()
    return (project_workspace / resolved_workspace).resolve()


def _build_provider_from_env(
    *,
    prefix: str,
    fallback_settings: OpenAICompatibleSettings,
    attachment_store: AttachmentStore,
) -> OpenAICompatibleProvider:
    if _has_provider_env(prefix):
        return OpenAICompatibleProvider(
            OpenAICompatibleSettings.from_env(prefix=prefix),
            attachment_store=attachment_store,
        )
    return OpenAICompatibleProvider(
        fallback_settings,
        attachment_store=attachment_store,
    )


def _has_provider_env(prefix: str) -> bool:
    api_key_name = f"{prefix}API_KEY"
    model_name = f"{prefix}MODEL"
    return bool(os.environ.get(api_key_name, "").strip()) and bool(
        os.environ.get(model_name, "").strip()
    )

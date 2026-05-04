from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models import LLMMessage, normalize_message_content
from ..orchestration import (
    DEFAULT_ROUTE_MODE,
    RouteMode,
    role_name_from_metadata,
    route_mode_from_metadata,
)
from ..runtime.sessions import ChatSession, SessionInfo


MAX_CHAT_IMAGES = 20
MAX_CHAT_FILES = 20


class ToolCallModel(BaseModel):
    id: str
    name: str
    arguments: str


class MessageModel(BaseModel):
    role: str
    content: str | list[dict[str, Any]]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCallModel] = Field(default_factory=list)


class SessionSummaryModel(BaseModel):
    name: str
    message_count: int
    updated_at: str


class SessionDetailModel(BaseModel):
    name: str
    updated_at: str
    compressed_summary: str = ""
    role_name: str = "default"
    route_mode: RouteMode = DEFAULT_ROUTE_MODE
    history: list[MessageModel] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    name: str | None = None


class SetCurrentSessionRequest(BaseModel):
    name: str


class RenameSessionRequest(BaseModel):
    name: str


class SetSessionRoleRequest(BaseModel):
    role_name: str


class SetSessionRouteModeRequest(BaseModel):
    route_mode: RouteMode


class ChatRequest(BaseModel):
    prompt: str
    session_name: str = "default"
    role_name: str | None = None
    route_mode: RouteMode | None = None
    response_language: str | None = Field(default=None, max_length=32)
    temperature: float | None = None
    max_tokens: int | None = None
    images: list["ChatImageInput"] = Field(
        default_factory=list,
        max_length=MAX_CHAT_IMAGES,
    )
    files: list["ChatFileInput"] = Field(
        default_factory=list,
        max_length=MAX_CHAT_FILES,
    )


class ChatImageInput(BaseModel):
    attachment_id: str


class ChatFileInput(BaseModel):
    attachment_id: str


class ImageAttachmentResponse(BaseModel):
    attachment_id: str
    url: str
    preview_url: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    original_filename: str = ""


class FileAttachmentResponse(BaseModel):
    attachment_id: str
    url: str
    download_url: str
    content_type: str
    size_bytes: int
    original_filename: str = ""
    workspace_path: str


class ChatResponse(BaseModel):
    session_name: str
    response: str
    response_content: str | list[dict[str, Any]] = ""
    updated_at: str
    steps: int
    compressed_summary: str = ""
    delegated: bool = False
    completed: bool = True
    job_id: str | None = None
    status: str = "completed"
    role_name: str = "default"


class ChatJobResponse(BaseModel):
    job_id: str
    session_name: str
    prompt: str
    role_name: str
    status: str
    attempt: int = 1
    retry_of_job_id: str | None = None
    can_retry: bool = False
    response: str = ""
    response_content: str | list[dict[str, Any]] = ""
    error: str = ""
    steps: int = 0
    pending_user_input: dict[str, Any] | None = None
    created_at: str
    started_at: str
    finished_at: str = ""
    updated_at: str


class ChatJobSummaryModel(BaseModel):
    job_id: str
    session_name: str
    prompt: str
    role_name: str
    status: str
    attempt: int = 1
    retry_of_job_id: str | None = None
    can_retry: bool = False
    error: str = ""
    created_at: str
    started_at: str
    finished_at: str = ""
    updated_at: str


class ChatJobsResponse(BaseModel):
    jobs: list[ChatJobSummaryModel] = Field(default_factory=list)


class ChatJobTraceResponse(BaseModel):
    job_id: str
    session_name: str
    status: str
    updated_at: str
    events: list[dict[str, Any]] = Field(default_factory=list)


class CronStatusResponse(BaseModel):
    enabled: bool = False
    jobs: int = 0
    next_run_at: str | None = None


class CronJobModel(BaseModel):
    id: str
    name: str
    enabled: bool = True
    schedule: str = ""
    payload_kind: str = "agent"
    session_name: str = "default"
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None


class CronJobsResponse(BaseModel):
    jobs: list[CronJobModel] = Field(default_factory=list)


class CronDeleteResponse(BaseModel):
    deleted: bool = True
    job_id: str


class HeartbeatConfigResponse(BaseModel):
    enabled: bool = False
    interval_seconds: int = 0
    file_path: str = ""
    content: str = ""
    has_meaningful_content: bool = False


class UpdateHeartbeatRequest(BaseModel):
    content: str = ""


class RoleSummaryModel(BaseModel):
    name: str
    editable: bool = True
    deletable: bool = True
    source_path: str | None = None


class RoleDetailModel(RoleSummaryModel):
    prompt: str = ""


class CreateRoleRequest(BaseModel):
    name: str
    prompt: str


class UpdateRoleRequest(BaseModel):
    prompt: str


class CharacterEmotionMapModel(BaseModel):
    emotion: str
    expression: str = ""
    motion: str = ""


class CharacterProfileModel(BaseModel):
    name: str
    editable: bool = True
    deletable: bool = True
    source_path: str | None = None
    prompt: str = ""
    model_profile_id: str = ""
    effective_model_profile_id: str = ""
    model_profile_label: str = ""
    chat_model: str = ""
    tts_voice: str = ""
    asr_model: str = ""
    live2d_selection_key: str = ""
    emotion_maps: list[CharacterEmotionMapModel] = Field(default_factory=list)


class CharacterProfilesResponse(BaseModel):
    active_model_profile_id: str = "a"
    characters: list[CharacterProfileModel] = Field(default_factory=list)
    model_profiles: list["ModelProfileModel"] = Field(default_factory=list)


class CreateCharacterProfileRequest(BaseModel):
    name: str
    prompt: str
    model_profile_id: str = ""
    emotion_maps: list[CharacterEmotionMapModel] = Field(default_factory=list)


class UpdateCharacterProfileRequest(BaseModel):
    prompt: str | None = None
    model_profile_id: str | None = None
    clear_model_profile_binding: bool = False
    emotion_maps: list[CharacterEmotionMapModel] | None = None


class CharacterPackageCharacterModel(BaseModel):
    name: str
    prompt: str
    model_profile_id: str = ""
    emotion_maps: list[CharacterEmotionMapModel] = Field(default_factory=list)


class CharacterProfilePackageModel(BaseModel):
    package_version: int = 1
    character: CharacterPackageCharacterModel
    model_profile_snapshot: dict[str, Any] = Field(default_factory=dict)


class StrictSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatModelProfileConfigModel(StrictSchemaModel):
    provider: str = "openai-compatible"
    model: str = ""
    base_url: str = ""
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=200000)
    api_key_configured: bool = False
    api_key_source: str = ""


class TTSModelProfileConfigModel(StrictSchemaModel):
    provider: str = ""
    model: str = ""
    base_url: str = ""
    voice: str = ""
    api_key_configured: bool = False
    api_key_source: str = ""


class ASRModelProfileConfigModel(StrictSchemaModel):
    provider: str = ""
    model: str = ""
    base_url: str = ""
    language: str = ""
    api_key_configured: bool = False
    api_key_source: str = ""


class Live2DModelProfileConfigModel(StrictSchemaModel):
    selection_key: str = ""


class ModelProfileModel(StrictSchemaModel):
    profile_id: str
    label: str
    chat: ChatModelProfileConfigModel = Field(default_factory=ChatModelProfileConfigModel)
    tts: TTSModelProfileConfigModel = Field(default_factory=TTSModelProfileConfigModel)
    asr: ASRModelProfileConfigModel = Field(default_factory=ASRModelProfileConfigModel)
    live2d: Live2DModelProfileConfigModel = Field(default_factory=Live2DModelProfileConfigModel)
    updated_at: str = ""


class ModelProfilesResponse(StrictSchemaModel):
    active_profile_id: str = "a"
    role_bindings: dict[str, str] = Field(default_factory=dict)
    profiles: list[ModelProfileModel] = Field(default_factory=list)


class CreateModelProfileRequest(StrictSchemaModel):
    label: str
    source_profile_id: str | None = None


class SetRoleModelProfileBindingRequest(StrictSchemaModel):
    profile_id: str


class UpdateChatModelProfileConfigRequest(StrictSchemaModel):
    provider: str = "openai-compatible"
    model: str = ""
    base_url: str = ""
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=200000)
    api_key: str | None = None
    clear_api_key: bool = False


class UpdateTTSModelProfileConfigRequest(StrictSchemaModel):
    provider: str = ""
    model: str = ""
    base_url: str = ""
    voice: str = ""
    api_key: str | None = None
    clear_api_key: bool = False


class UpdateASRModelProfileConfigRequest(StrictSchemaModel):
    provider: str = ""
    model: str = ""
    base_url: str = ""
    language: str = ""
    api_key: str | None = None
    clear_api_key: bool = False


class UpdateModelProfileRequest(StrictSchemaModel):
    label: str | None = None
    chat: UpdateChatModelProfileConfigRequest | None = None
    tts: UpdateTTSModelProfileConfigRequest | None = None
    asr: UpdateASRModelProfileConfigRequest | None = None
    live2d: Live2DModelProfileConfigModel | None = None


class TTSRequest(BaseModel):
    text: str
    provider: str | None = None
    voice: str | None = None
    rate: str | None = None
    volume: str | None = None
    pitch: str | None = None


class TTSVoiceModel(BaseModel):
    name: str
    short_name: str
    locale: str = ""
    gender: str = ""
    display_name: str = ""


class TTSVoicesResponse(BaseModel):
    provider: str
    voices: list[TTSVoiceModel] = Field(default_factory=list)


class WebTTSProviderModel(BaseModel):
    name: str
    label: str
    available: bool = True
    state: str = "ready"
    detail: str = ""


class WebTTSConfigModel(BaseModel):
    default_provider: str = "edge"
    default_voice: str = ""
    default_voices: dict[str, str] = Field(default_factory=dict)
    providers: list[WebTTSProviderModel] = Field(default_factory=list)


class WebSpeechProviderModel(BaseModel):
    kind: str = "asr"
    name: str = ""
    label: str = ""
    selected: bool = False
    available: bool = False
    state: str = "missing"
    detail: str = ""
    resource_directory: str = ""


class WebASRConfigModel(BaseModel):
    available: bool = False
    state: str = "missing"
    detail: str = ""
    sample_rate: int = 16000
    selected_asr_provider: str = ""
    selected_vad_provider: str = ""
    always_listen_supported: bool = False
    asr_providers: list[WebSpeechProviderModel] = Field(default_factory=list)
    vad_providers: list[WebSpeechProviderModel] = Field(default_factory=list)


class UpdateWebASRProviderRequest(BaseModel):
    provider: str = ""


class WebLive2DExpressionModel(BaseModel):
    name: str = ""
    file: str = ""
    url: str = ""
    note: str = ""


class WebLive2DMotionModel(WebLive2DExpressionModel):
    group: str = ""
    index: int = 0


class WebLive2DHotkeyModel(BaseModel):
    hotkey_key: str = ""
    hotkey_id: str = ""
    name: str = ""
    action: str = ""
    file: str = ""
    shortcut_tokens: list[str] = Field(default_factory=list)
    shortcut_label: str = ""
    target_kind: str = ""
    supported: bool = False


class UpdateWebLive2DAnnotationRequest(BaseModel):
    selection_key: str = ""
    kind: str = ""
    file: str = ""
    note: str = ""


class WebLive2DAnnotationResponse(BaseModel):
    selection_key: str = ""
    kind: str = ""
    file: str = ""
    note: str = ""


class UpdateWebLive2DHotkeyRequest(BaseModel):
    selection_key: str = ""
    hotkey_key: str = ""
    shortcut_tokens: list[str] = Field(default_factory=list)
    restore_default: bool = False


class WebLive2DHotkeyResponse(WebLive2DHotkeyModel):
    selection_key: str = ""


class WebLive2DModelOptionModel(BaseModel):
    source: str = ""
    selection_key: str = ""
    model_name: str = ""
    model_url: str = ""
    directory_name: str = ""
    lip_sync_parameter_ids: list[str] = Field(default_factory=list)
    mouth_form_parameter_id: str | None = None
    expressions: list[WebLive2DExpressionModel] = Field(default_factory=list)
    motions: list[WebLive2DMotionModel] = Field(default_factory=list)
    hotkeys: list[WebLive2DHotkeyModel] = Field(default_factory=list)
    annotations_writable: bool = False


class WebLive2DConfigModel(WebLive2DModelOptionModel):
    available: bool = False
    models: list[WebLive2DModelOptionModel] = Field(default_factory=list)


class WebStageBackgroundModel(BaseModel):
    key: str = "default"
    label: str = "不使用背景"
    url: str = ""
    kind: str = "none"


class WebStageConfigModel(BaseModel):
    default_background_key: str = "default"
    backgrounds: list[WebStageBackgroundModel] = Field(default_factory=list)


class WebRuntimeConfigModel(BaseModel):
    delegated_ack_enabled: bool = True
    shell_safety_mode: str = "workspace-write"
    file_write_enabled: bool = True
    cron_mutation_enabled: bool = True
    web_private_network_enabled: bool = False


class WebConfigResponse(BaseModel):
    session_name: str = "default"
    role_name: str = "default"
    route_mode: RouteMode = DEFAULT_ROUTE_MODE
    model_profile_scope: str = "default"
    model_profiles: ModelProfilesResponse = Field(default_factory=ModelProfilesResponse)
    runtime: WebRuntimeConfigModel = Field(default_factory=WebRuntimeConfigModel)
    live2d: WebLive2DConfigModel = Field(default_factory=WebLive2DConfigModel)
    stage: WebStageConfigModel = Field(default_factory=WebStageConfigModel)
    asr: WebASRConfigModel = Field(default_factory=WebASRConfigModel)
    tts: WebTTSConfigModel = Field(default_factory=WebTTSConfigModel)


class UpdateWebRuntimeConfigRequest(BaseModel):
    delegated_ack_enabled: bool | None = None
    shell_safety_mode: str | None = None
    file_write_enabled: bool | None = None
    cron_mutation_enabled: bool | None = None
    web_private_network_enabled: bool | None = None


class ASRTranscriptionResponse(BaseModel):
    text: str = ""
    language: str = ""


def message_model_from_message(
    message: LLMMessage,
    *,
    sanitize_user_content: bool = False,
) -> MessageModel:
    del sanitize_user_content
    content = normalize_message_content(message.content)

    return MessageModel(
        role=message.role,
        content=content,
        name=message.name,
        tool_call_id=message.tool_call_id,
        tool_calls=[
            ToolCallModel(
                id=tool_call.id,
                name=tool_call.name,
                arguments=tool_call.arguments,
            )
            for tool_call in message.tool_calls
        ],
    )


def session_summary_model_from_info(info: SessionInfo) -> SessionSummaryModel:
    return SessionSummaryModel(
        name=info.name,
        message_count=info.message_count,
        updated_at=info.updated_at,
    )


def session_detail_model_from_session(session: ChatSession) -> SessionDetailModel:
    return SessionDetailModel(
        name=session.name,
        updated_at=session.updated_at,
        compressed_summary=session.compressed_summary,
        role_name=role_name_from_metadata(session.metadata),
        route_mode=route_mode_from_metadata(session.metadata),
        history=[
            message_model_from_message(
                message,
                sanitize_user_content=True,
            )
            for message in session.history
        ],
    )


CHANNEL_SECRET_FIELD_NAMES = {
    "api_key",
    "bot_token",
    "client_secret",
    "password",
    "secret",
    "token",
    "webhook_secret",
}


def channel_config_payload(config: dict[str, Any]) -> dict[str, Any]:
    return {
        str(channel_name): _redact_channel_config(channel_config)
        for channel_name, channel_config in dict(config).items()
    }


def _redact_channel_config(channel_config: Any) -> Any:
    if not isinstance(channel_config, dict):
        return channel_config

    payload: dict[str, Any] = {}
    for key, value in channel_config.items():
        key_text = str(key)
        if _is_secret_channel_field(key_text):
            payload[key_text] = ""
            payload[f"{key_text}_configured"] = bool(str(value or "").strip())
            continue
        payload[key_text] = value
    return payload


def _is_secret_channel_field(field_name: str) -> bool:
    normalized = field_name.strip().lower()
    return normalized in CHANNEL_SECRET_FIELD_NAMES

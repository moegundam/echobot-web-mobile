from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from echobot import AgentCore, AgentTraceStore, LLMMessage, LLMResponse
from echobot.attachments import AttachmentStore
from echobot.asr import ASRStatusSnapshot, ProviderStatusSnapshot, TranscriptionResult
from echobot.app import create_app
from echobot.app.auth import DEFAULT_TRUSTED_USER_HEADER, user_storage_key
from echobot.app.services.model_profiles import ModelProfileService
from echobot.app.services.runtime_model_repositories import (
    LLMModelRepository,
    Live2DModelRepository,
    VoiceModelRepository,
)
from echobot.app.web_pages import WEB_PAGE_ROUTES
from echobot.channels import ChannelAddress
from echobot.orchestration import (
    ConversationCoordinator,
    DecisionEngine,
    RoleCardRegistry,
    RoleplayEngine,
)
from echobot.providers.base import LLMProvider
from echobot.runtime.bootstrap import RuntimeContext, RuntimeOptions
from echobot.runtime.settings import (
    DEFAULT_SHELL_SAFETY_MODE,
    RuntimeConfigSnapshot,
    RuntimeControls,
    RuntimeSettingsStore,
)
from echobot.runtime.session_runner import SessionAgentRunner
from echobot.runtime.sessions import SessionStore
from echobot.scheduling.cron import (
    CronJob,
    CronJobState,
    CronPayload,
    CronSchedule,
    CronService,
    CronStore,
)
from echobot.scheduling.heartbeat import HeartbeatService
from echobot.tts import (
    SynthesizedSpeech,
    TTSProvider,
    TTSSynthesisOptions,
    TTSService,
    VoiceOption,
)
from echobot.app.routers.stage import subscribe_stage_events


os.environ.setdefault("ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD", "false")
os.environ.setdefault("ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD", "false")


def make_chat_png_bytes() -> bytes:
    image = Image.new("RGBA", (2, 2), (255, 0, 0, 128))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def make_chat_text_bytes() -> bytes:
    return "hello from uploaded file\n".encode("utf-8")


def _wait_for_session_messages(
    client: TestClient,
    session_name: str,
    message_count: int,
    *,
    attempts: int = 50,
) -> dict[str, object]:
    detail = client.get(f"/api/sessions/{quote(session_name)}")
    for _ in range(attempts):
        detail = client.get(f"/api/sessions/{quote(session_name)}")
        if detail.status_code == 200 and len(detail.json().get("history", [])) >= message_count:
            return detail.json()
        time.sleep(0.02)
    return detail.json()


class FakeProvider(LLMProvider):
    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del tools, tool_choice, temperature, max_tokens
        system_text = "\n".join(
            message.content_text
            for message in messages
            if getattr(message, "role", "") == "system"
        )
        user_text = messages[-1].content_text if messages else ""
        if "The system decided this request needs the full agent" in system_text:
            content = "working"
        elif user_text.startswith("The full agent finished the task."):
            content = "done"
        elif user_text.startswith("The full agent failed while handling the task."):
            content = "failed"
        else:
            content = "pong"
        return LLMResponse(
            message=LLMMessage(role="assistant", content=content),
            model="fake-model",
        )

    async def stream_generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ):
        response = await self.generate(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.message.content
        if not content:
            return
        midpoint = max(len(content) // 2, 1)
        yield content[:midpoint]
        if midpoint < len(content):
            yield content[midpoint:]


class SlowAgentProvider(LLMProvider):
    async def generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ) -> LLMResponse:
        del messages, tools, tool_choice, temperature, max_tokens
        await asyncio.sleep(2)
        return LLMResponse(
            message=LLMMessage(role="assistant", content="done-late"),
            model="slow-fake-model",
        )


class SlowAckProvider(FakeProvider):
    async def stream_generate(
        self,
        messages,
        *,
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
    ):
        response = await self.generate(
            messages,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.message.content
        if not content:
            return
        midpoint = max(len(content) // 2, 1)
        yield content[:midpoint]
        await asyncio.sleep(0.1)
        if midpoint < len(content):
            yield content[midpoint:]


class FakeTTSProvider(TTSProvider):
    name = "edge"
    label = "Fake Edge TTS"

    @property
    def default_voice(self) -> str:
        return "zh-CN-XiaoxiaoNeural"

    async def list_voices(self) -> list[VoiceOption]:
        return [
            VoiceOption(
                name="Microsoft Xiaoxiao Online (Natural)",
                short_name="zh-CN-XiaoxiaoNeural",
                locale="zh-CN",
                gender="Female",
                display_name="Xiaoxiao",
            ),
        ]

    async def synthesize(
        self,
        *,
        text: str,
        options: TTSSynthesisOptions | None = None,
    ) -> SynthesizedSpeech:
        selected_voice = (options.voice if options else None) or self.default_voice
        payload = f"fake-audio:{selected_voice}:{text}".encode("utf-8")
        return SynthesizedSpeech(
            audio_bytes=payload,
            content_type="audio/mpeg",
            file_extension="mp3",
            provider=self.name,
            voice=selected_voice,
        )


class FakeKokoroTTSProvider(TTSProvider):
    name = "kokoro"
    label = "Fake Sherpa Kokoro"

    @property
    def default_voice(self) -> str:
        return "zf_001"

    async def list_voices(self) -> list[VoiceOption]:
        return [
            VoiceOption(
                name="zf_001 (3)",
                short_name="zf_001",
                locale="zh-CN",
                gender="Female",
                display_name="Chinese zf_001",
            ),
            VoiceOption(
                name="af_maple (0)",
                short_name="af_maple",
                locale="en-US",
                gender="Female",
                display_name="American af_maple",
            ),
        ]

    async def synthesize(
        self,
        *,
        text: str,
        options: TTSSynthesisOptions | None = None,
    ) -> SynthesizedSpeech:
        selected_voice = (options.voice if options else None) or self.default_voice
        payload = f"fake-kokoro:{selected_voice}:{text}".encode("utf-8")
        return SynthesizedSpeech(
            audio_bytes=payload,
            content_type="audio/wav",
            file_extension="wav",
            provider=self.name,
            voice=selected_voice,
        )


class FakeRealtimeASRSession:
    async def accept_audio_bytes(self, audio_bytes: bytes) -> list[dict[str, object]]:
        if not audio_bytes:
            return []
        text = audio_bytes.decode("utf-8", errors="ignore").strip() or "voice"
        return [
            {
                "type": "transcript",
                "text": text,
                "language": "zh",
                "final": True,
                "start_ms": 0,
            }
        ]

    async def flush(self) -> list[dict[str, object]]:
        return []

    async def reset(self) -> None:
        return None


class FakeASRService:
    def __init__(self) -> None:
        self.selected_asr_provider = "fake-asr"

    async def on_startup(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def status_snapshot(self) -> ASRStatusSnapshot:
        return ASRStatusSnapshot(
            available=True,
            state="ready",
            detail="ASR ready",
            sample_rate=16000,
            selected_asr_provider=self.selected_asr_provider,
            selected_vad_provider="fake-vad",
            always_listen_supported=True,
            asr_providers=[
                ProviderStatusSnapshot(
                    kind="asr",
                    name="fake-asr",
                    label="Fake ASR",
                    selected=self.selected_asr_provider == "fake-asr",
                    available=True,
                    state="ready",
                    detail="ASR ready",
                    resource_directory="D:/fake-models/asr",
                ),
                ProviderStatusSnapshot(
                    kind="asr",
                    name="backup-asr",
                    label="Backup ASR",
                    selected=self.selected_asr_provider == "backup-asr",
                    available=True,
                    state="ready",
                    detail="Backup ASR ready",
                    resource_directory="D:/fake-models/asr-backup",
                ),
            ],
            vad_providers=[
                ProviderStatusSnapshot(
                    kind="vad",
                    name="fake-vad",
                    label="Fake VAD",
                    selected=True,
                    available=True,
                    state="ready",
                    detail="VAD ready",
                    resource_directory="D:/fake-models/vad",
                )
            ],
        )

    async def transcribe_wav_bytes(self, audio_bytes: bytes) -> TranscriptionResult:
        text = f"voice-{len(audio_bytes)}" if audio_bytes else ""
        return TranscriptionResult(text=text, language="zh")

    async def create_realtime_session(self) -> FakeRealtimeASRSession:
        return FakeRealtimeASRSession()

    async def set_selected_asr_provider(self, provider_name: str) -> None:
        normalized_name = provider_name.strip()
        if normalized_name not in {"fake-asr", "backup-asr"}:
            raise ValueError(f"Unknown ASR provider: {provider_name}")
        self.selected_asr_provider = normalized_name


def build_test_context(options: RuntimeOptions) -> RuntimeContext:
    workspace = (options.workspace or Path(".")).resolve()
    storage_root = _storage_root_for_options(options, workspace)
    agent = AgentCore(FakeProvider())
    session_store = SessionStore(storage_root / "sessions")
    agent_session_store = SessionStore(storage_root / "agent_sessions")
    trace_store = AgentTraceStore(storage_root / "agent_traces")
    session_runner = SessionAgentRunner(
        agent,
        agent_session_store,
        trace_store=trace_store,
    )
    role_registry = RoleCardRegistry.discover(project_root=workspace)
    coordinator = ConversationCoordinator(
        session_store=session_store,
        agent_runner=session_runner,
        decision_engine=DecisionEngine(),
        roleplay_engine=RoleplayEngine(AgentCore(FakeProvider()), role_registry),
        role_registry=role_registry,
        delegated_ack_enabled=_delegated_ack_enabled(options),
    )
    heartbeat_service = None
    if not options.no_heartbeat:
        heartbeat_service = HeartbeatService(
            heartbeat_file=workspace / ".echobot" / "HEARTBEAT.md",
            provider=FakeProvider(),
            interval_seconds=60,
        )
    return RuntimeContext(
        workspace=workspace,
        attachment_store=AttachmentStore(storage_root / "attachments"),
        supports_image_input=True,
        agent=agent,
        session_store=session_store,
        agent_session_store=agent_session_store,
        session=None,
        tool_registry=None,
        skill_registry=None,
        cron_service=CronService(storage_root / "cron" / "jobs.json"),
        heartbeat_service=heartbeat_service,
        session_runner=session_runner,
        coordinator=coordinator,
        role_registry=role_registry,
        memory_support=None,
        heartbeat_file_path=storage_root / "HEARTBEAT.md",
        heartbeat_interval_seconds=60,
        tool_registry_factory=lambda *_args: None,
        runtime_controls=_runtime_controls(options),
        default_runtime_config=_default_runtime_config(options),
        storage_root=storage_root,
    )


def build_slow_agent_test_context(options: RuntimeOptions) -> RuntimeContext:
    workspace = (options.workspace or Path(".")).resolve()
    storage_root = _storage_root_for_options(options, workspace)
    agent = AgentCore(SlowAgentProvider())
    session_store = SessionStore(storage_root / "sessions")
    agent_session_store = SessionStore(storage_root / "agent_sessions")
    trace_store = AgentTraceStore(storage_root / "agent_traces")
    session_runner = SessionAgentRunner(
        agent,
        agent_session_store,
        trace_store=trace_store,
    )
    role_registry = RoleCardRegistry.discover(project_root=workspace)
    coordinator = ConversationCoordinator(
        session_store=session_store,
        agent_runner=session_runner,
        decision_engine=DecisionEngine(),
        roleplay_engine=RoleplayEngine(AgentCore(FakeProvider()), role_registry),
        role_registry=role_registry,
        delegated_ack_enabled=_delegated_ack_enabled(options),
    )
    heartbeat_service = None
    if not options.no_heartbeat:
        heartbeat_service = HeartbeatService(
            heartbeat_file=workspace / ".echobot" / "HEARTBEAT.md",
            provider=FakeProvider(),
            interval_seconds=60,
        )
    return RuntimeContext(
        workspace=workspace,
        attachment_store=AttachmentStore(storage_root / "attachments"),
        supports_image_input=True,
        agent=agent,
        session_store=session_store,
        agent_session_store=agent_session_store,
        session=None,
        tool_registry=None,
        skill_registry=None,
        cron_service=CronService(storage_root / "cron" / "jobs.json"),
        heartbeat_service=heartbeat_service,
        session_runner=session_runner,
        coordinator=coordinator,
        role_registry=role_registry,
        memory_support=None,
        heartbeat_file_path=storage_root / "HEARTBEAT.md",
        heartbeat_interval_seconds=60,
        tool_registry_factory=lambda *_args: None,
        runtime_controls=_runtime_controls(options),
        default_runtime_config=_default_runtime_config(options),
        storage_root=storage_root,
    )


def build_slow_ack_test_context(options: RuntimeOptions) -> RuntimeContext:
    workspace = (options.workspace or Path(".")).resolve()
    storage_root = _storage_root_for_options(options, workspace)
    agent = AgentCore(FakeProvider())
    session_store = SessionStore(storage_root / "sessions")
    agent_session_store = SessionStore(storage_root / "agent_sessions")
    trace_store = AgentTraceStore(storage_root / "agent_traces")
    session_runner = SessionAgentRunner(
        agent,
        agent_session_store,
        trace_store=trace_store,
    )
    role_registry = RoleCardRegistry.discover(project_root=workspace)
    coordinator = ConversationCoordinator(
        session_store=session_store,
        agent_runner=session_runner,
        decision_engine=DecisionEngine(),
        roleplay_engine=RoleplayEngine(AgentCore(SlowAckProvider()), role_registry),
        role_registry=role_registry,
        delegated_ack_enabled=_delegated_ack_enabled(options),
    )
    heartbeat_service = None
    if not options.no_heartbeat:
        heartbeat_service = HeartbeatService(
            heartbeat_file=workspace / ".echobot" / "HEARTBEAT.md",
            provider=FakeProvider(),
            interval_seconds=60,
        )
    return RuntimeContext(
        workspace=workspace,
        attachment_store=AttachmentStore(storage_root / "attachments"),
        supports_image_input=True,
        agent=agent,
        session_store=session_store,
        agent_session_store=agent_session_store,
        session=None,
        tool_registry=None,
        skill_registry=None,
        cron_service=CronService(storage_root / "cron" / "jobs.json"),
        heartbeat_service=heartbeat_service,
        session_runner=session_runner,
        coordinator=coordinator,
        role_registry=role_registry,
        memory_support=None,
        heartbeat_file_path=storage_root / "HEARTBEAT.md",
        heartbeat_interval_seconds=60,
        tool_registry_factory=lambda *_args: None,
        runtime_controls=_runtime_controls(options),
        default_runtime_config=_default_runtime_config(options),
        storage_root=storage_root,
    )


def build_test_tts_service(_workspace: Path) -> TTSService:
    return TTSService(
        {
            "edge": FakeTTSProvider(),
            "kokoro": FakeKokoroTTSProvider(),
        },
        default_provider="edge",
    )


def build_test_asr_service(_workspace: Path) -> FakeASRService:
    return FakeASRService()


def _storage_root_for_options(options: RuntimeOptions, workspace: Path) -> Path:
    if options.storage_root is None:
        return workspace / ".echobot"
    storage_root = Path(options.storage_root).expanduser()
    if storage_root.is_absolute():
        return storage_root.resolve()
    return (workspace / storage_root).resolve()


def _delegated_ack_enabled(options: RuntimeOptions) -> bool:
    if options.delegated_ack_enabled is None:
        store = RuntimeSettingsStore(
            (options.workspace or Path(".")).resolve()
            / ".echobot"
            / "runtime_settings.json",
        )
        return store.load().delegated_ack_enabled is not False
    return bool(options.delegated_ack_enabled)


def _runtime_controls(options: RuntimeOptions) -> RuntimeControls:
    store = RuntimeSettingsStore(
        (options.workspace or Path(".")).resolve()
        / ".echobot"
        / "runtime_settings.json",
    )
    settings = store.load()
    shell_safety_mode = settings.shell_safety_mode or DEFAULT_SHELL_SAFETY_MODE
    return RuntimeControls(
        shell_safety_mode=shell_safety_mode,
        file_write_enabled=(
            True if settings.file_write_enabled is None else settings.file_write_enabled
        ),
        cron_mutation_enabled=(
            True
            if settings.cron_mutation_enabled is None
            else settings.cron_mutation_enabled
        ),
        web_private_network_enabled=(
            False
            if settings.web_private_network_enabled is None
            else settings.web_private_network_enabled
        ),
    )


def _default_runtime_config(options: RuntimeOptions) -> RuntimeConfigSnapshot:
    return RuntimeConfigSnapshot(
        delegated_ack_enabled=(
            True
            if options.delegated_ack_enabled is None
            else bool(options.delegated_ack_enabled)
        ),
        shell_safety_mode=DEFAULT_SHELL_SAFETY_MODE,
        file_write_enabled=True,
        cron_mutation_enabled=True,
        web_private_network_enabled=False,
    )


def write_test_live2d_model(workspace: Path) -> None:
    model_dir = workspace / ".echobot" / "live2d" / "兔兔"
    texture_dir = model_dir / "兔兔 .4096"
    texture_dir.mkdir(parents=True, exist_ok=True)

    model_payload = {
        "Version": 3,
        "FileReferences": {
            "Moc": "兔兔 .moc3",
            "Textures": [
                "兔兔 .4096/texture_00.png",
            ],
            "DisplayInfo": "兔兔 .cdi3.json",
        },
    }
    display_info_payload = {
        "Version": 3,
        "Parameters": [
            {"Id": "ParamMouthOpenY", "Name": "嘴巴开合"},
            {"Id": "ParamMouthForm", "Name": "嘴型"},
        ],
    }

    (model_dir / "兔兔 .model3.json").write_text(
        json.dumps(model_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "兔兔 .cdi3.json").write_text(
        json.dumps(display_info_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "兔兔 .moc3").write_bytes(b"fake-moc3")
    (texture_dir / "texture_00.png").write_bytes(b"fake-png")


def write_test_hiyori_live2d_model(workspace: Path) -> None:
    model_dir = workspace / ".echobot" / "live2d" / "hiyori_pro_en" / "runtime"
    texture_dir = model_dir / "hiyori_pro_t11.2048"
    texture_dir.mkdir(parents=True, exist_ok=True)

    model_payload = {
        "Version": 3,
        "FileReferences": {
            "Moc": "hiyori_pro_t11.moc3",
            "Textures": [
                "hiyori_pro_t11.2048/texture_00.png",
            ],
            "DisplayInfo": "hiyori_pro_t11.cdi3.json",
        },
    }
    display_info_payload = {
        "Version": 3,
        "Parameters": [
            {"Id": "ParamMouthOpenY", "Name": "Mouth Open"},
            {"Id": "ParamMouthForm", "Name": "Mouth Form"},
        ],
    }

    (model_dir / "hiyori_pro_t11.model3.json").write_text(
        json.dumps(model_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "hiyori_pro_t11.cdi3.json").write_text(
        json.dumps(display_info_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "hiyori_pro_t11.moc3").write_bytes(b"fake-moc3")
    (texture_dir / "texture_00.png").write_bytes(b"fake-png")


def write_test_vtube_live2d_model(workspace: Path) -> None:
    model_dir = workspace / ".echobot" / "live2d" / "yumi"
    texture_dir = model_dir / "textures"
    texture_dir.mkdir(parents=True, exist_ok=True)

    model_payload = {
        "Version": 3,
        "FileReferences": {
            "Moc": "yumi.moc3",
            "Textures": [
                "textures/texture_00.png",
            ],
            "DisplayInfo": "yumi.cdi3.json",
        },
        "Groups": [
            {
                "Target": "Parameter",
                "Name": "LipSync",
                "Ids": ["ParamMouthOpenY"],
            },
        ],
    }
    display_info_payload = {
        "Version": 3,
        "Parameters": [
            {"Id": "ParamMouthOpenY", "Name": "Mouth Open"},
            {"Id": "ParamMouthForm", "Name": "Mouth Form"},
            {"Id": "ParamEyeSmile", "Name": "Smile"},
        ],
    }
    vtube_payload = {
        "FileReferences": {
            "Model": "yumi.model3.json",
            "IdleAnimation": "wave.motion3.json",
        },
        "Hotkeys": [
            {
                "HotkeyID": "hk_exp_smile",
                "Name": "Smile",
                "Action": "ToggleExpression",
                "File": "smile.exp3.json",
                "Triggers": {
                    "Trigger1": "Alt",
                    "Trigger2": "N1",
                    "Trigger3": "",
                    "ScreenButton": -1,
                },
            },
            {
                "HotkeyID": "hk_motion_wave",
                "Name": "Wave",
                "Action": "TriggerAnimation",
                "File": "wave.motion3.json",
                "Triggers": {
                    "Trigger1": "LeftControl",
                    "Trigger2": "F3",
                    "Trigger3": "",
                    "ScreenButton": -1,
                },
            },
            {
                "HotkeyID": "hk_clear",
                "Name": "Clear Expressions",
                "Action": "RemoveAllExpressions",
                "File": "",
                "Triggers": {
                    "Trigger1": "LeftControl",
                    "Trigger2": "Tab",
                    "Trigger3": "Space",
                    "ScreenButton": -1,
                },
            },
        ],
    }
    smile_expression_payload = {
        "Type": "Live2D Expression",
        "Parameters": [
            {"Id": "ParamEyeSmile", "Value": 1.0, "Blend": "Add"},
        ],
    }
    sad_expression_payload = {
        "Type": "Live2D Expression",
        "Parameters": [
            {"Id": "ParamMouthForm", "Value": -1.0, "Blend": "Set"},
        ],
    }
    motion_payload = {
        "Version": 3,
        "Meta": {
            "Duration": 1.0,
            "Loop": False,
            "AreBeziersRestricted": True,
            "CurveCount": 0,
            "TotalSegmentCount": 0,
            "TotalPointCount": 0,
            "UserDataCount": 0,
            "TotalUserDataSize": 0,
            "Fps": 30,
        },
        "Curves": [],
        "UserData": [],
    }
    annotations_payload = {
        "version": 1,
        "expressions": {
            "smile.exp3.json": "默认笑脸",
        },
        "motions": {},
        "hotkeys": {},
    }

    (model_dir / "yumi.model3.json").write_text(
        json.dumps(model_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "yumi.cdi3.json").write_text(
        json.dumps(display_info_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "yumi.vtube.json").write_text(
        json.dumps(vtube_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "smile.exp3.json").write_text(
        json.dumps(smile_expression_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "sad.exp3.json").write_text(
        json.dumps(sad_expression_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "wave.motion3.json").write_text(
        json.dumps(motion_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "jump.motion3.json").write_text(
        json.dumps(motion_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (model_dir / "echobot.live2d.json").write_text(
        json.dumps(annotations_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (model_dir / "yumi.moc3").write_bytes(b"fake-yumi-moc3")
    (texture_dir / "texture_00.png").write_bytes(b"fake-png")


def write_test_split_runtime_live2d_models(workspace: Path) -> None:
    base_dir = workspace / ".echobot" / "live2d" / "duo"
    runtime_specs = [
        {
            "runtime_name": "alpha",
            "model_name": "alpha",
            "parameter_id": "ParamAlphaSmile",
            "default_note": "alpha default note",
            "function_key": "F1",
        },
        {
            "runtime_name": "beta",
            "model_name": "beta",
            "parameter_id": "ParamBetaSmile",
            "default_note": "beta default note",
            "function_key": "F2",
        },
    ]

    for runtime_spec in runtime_specs:
        runtime_dir = base_dir / runtime_spec["runtime_name"]
        texture_dir = runtime_dir / "textures"
        texture_dir.mkdir(parents=True, exist_ok=True)

        model_payload = {
            "Version": 3,
            "FileReferences": {
                "Moc": f"{runtime_spec['model_name']}.moc3",
                "Textures": [
                    "textures/texture_00.png",
                ],
                "DisplayInfo": f"{runtime_spec['model_name']}.cdi3.json",
            },
        }
        display_info_payload = {
            "Version": 3,
            "Parameters": [
                {"Id": "ParamMouthOpenY", "Name": "Mouth Open"},
                {"Id": runtime_spec["parameter_id"], "Name": "Smile"},
            ],
        }
        vtube_payload = {
            "FileReferences": {
                "Model": f"{runtime_spec['model_name']}.model3.json",
            },
            "Hotkeys": [
                {
                    "HotkeyID": "hk_smile",
                    "Name": "Smile",
                    "Action": "ToggleExpression",
                    "File": "smile.exp3.json",
                    "Triggers": {
                        "Trigger1": "LeftControl",
                        "Trigger2": runtime_spec["function_key"],
                        "Trigger3": "",
                        "ScreenButton": -1,
                    },
                },
            ],
        }
        expression_payload = {
            "Type": "Live2D Expression",
            "Parameters": [
                {"Id": runtime_spec["parameter_id"], "Value": 1.0, "Blend": "Add"},
            ],
        }
        annotations_payload = {
            "version": 1,
            "expressions": {
                "smile.exp3.json": runtime_spec["default_note"],
            },
            "motions": {},
            "hotkeys": {},
        }

        (runtime_dir / f"{runtime_spec['model_name']}.model3.json").write_text(
            json.dumps(model_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        (runtime_dir / f"{runtime_spec['model_name']}.cdi3.json").write_text(
            json.dumps(display_info_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        (runtime_dir / f"{runtime_spec['model_name']}.vtube.json").write_text(
            json.dumps(vtube_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        (runtime_dir / "smile.exp3.json").write_text(
            json.dumps(expression_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        (runtime_dir / "echobot.live2d.json").write_text(
            json.dumps(annotations_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (runtime_dir / f"{runtime_spec['model_name']}.moc3").write_bytes(b"fake-moc3")
        (texture_dir / "texture_00.png").write_bytes(b"fake-png")


def write_test_cron_jobs(workspace: Path) -> None:
    cron_store_path = workspace / ".echobot" / "cron" / "jobs.json"
    cron_store_path.parent.mkdir(parents=True, exist_ok=True)
    store = CronStore(
        jobs=[
            CronJob(
                id="job_enabled",
                name="Morning summary",
                enabled=True,
                schedule=CronSchedule(kind="every", every_seconds=3600),
                payload=CronPayload(
                    kind="agent",
                    content="Summarize today's priorities",
                    session_name="default",
                ),
                state=CronJobState(
                    next_run_at="2030-01-01T09:00:00+08:00",
                    last_run_at="2030-01-01T08:00:00+08:00",
                    last_status="ok",
                ),
                created_at="2030-01-01T07:30:00+08:00",
                updated_at="2030-01-01T08:00:00+08:00",
            ),
            CronJob(
                id="job_disabled",
                name="Disabled reminder",
                enabled=False,
                schedule=CronSchedule(kind="cron", expr="0 9 * * 1-5", timezone="Asia/Shanghai"),
                payload=CronPayload(
                    kind="text",
                    content="Standup time",
                    session_name="team",
                ),
                state=CronJobState(
                    last_run_at="2030-01-01T07:55:00+08:00",
                    last_status="error",
                    last_error="network timeout",
                ),
                created_at="2030-01-01T07:00:00+08:00",
                updated_at="2030-01-01T07:55:00+08:00",
            ),
        ]
    )
    cron_store_path.write_text(
        json.dumps(store.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_test_heartbeat_file(workspace: Path, content: str) -> None:
    heartbeat_file_path = workspace / ".echobot" / "HEARTBEAT.md"
    heartbeat_file_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_file_path.write_text(content, encoding="utf-8")


def update_split_model_profile(
    client: TestClient,
    profile_id: str,
    *,
    label: str | None = None,
    chat: dict[str, object] | None = None,
    tts: dict[str, object] | None = None,
    asr: dict[str, object] | None = None,
    live2d: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
):
    if label is not None or chat is not None:
        body: dict[str, object] = {}
        if label is not None:
            body["name"] = label
        if chat:
            body.update(chat)
        response = client.patch(
            f"/api/llm-models/{profile_id}",
            headers=headers,
            json=body,
        )
        if response.status_code >= 400:
            return response

    if label is not None or tts is not None or asr is not None:
        body = {}
        if label is not None:
            body["name"] = label
        if tts is not None:
            body["tts"] = tts
        if asr is not None:
            body["stt"] = asr
        response = client.patch(
            f"/api/voice-models/{profile_id}",
            headers=headers,
            json=body,
        )
        if response.status_code >= 400:
            return response

    if label is not None or live2d is not None:
        body = {}
        if label is not None:
            body["name"] = label
        if live2d is not None:
            body["selection_key"] = live2d.get("selection_key", "")
        response = client.patch(
            f"/api/live2d-models/{profile_id}",
            headers=headers,
            json=body,
        )
        if response.status_code >= 400:
            return response

    return client.get(f"/api/model-profiles/{profile_id}", headers=headers)


def create_split_model_profile(
    client: TestClient,
    *,
    name: str,
    source_profile_id: str | None = None,
    headers: dict[str, str] | None = None,
):
    body = {"name": name, "source_profile_id": source_profile_id}
    llm = client.post("/api/llm-models", headers=headers, json=body)
    if llm.status_code >= 400:
        return llm
    voice = client.post("/api/voice-models", headers=headers, json=body)
    if voice.status_code >= 400:
        return voice
    live2d = client.post("/api/live2d-models", headers=headers, json=body)
    if live2d.status_code >= 400:
        return live2d
    return client.get(f"/api/model-profiles/{llm.json()['id']}", headers=headers)


def activate_split_model_profile(
    client: TestClient,
    profile_id: str,
    *,
    headers: dict[str, str] | None = None,
):
    llm = client.post(f"/api/llm-models/{profile_id}/activate", headers=headers)
    if llm.status_code >= 400:
        return llm
    voice = client.post(f"/api/voice-models/{profile_id}/activate", headers=headers)
    if voice.status_code >= 400:
        return voice
    live2d = client.post(f"/api/live2d-models/{profile_id}/activate", headers=headers)
    if live2d.status_code >= 400:
        return live2d
    return client.get("/api/model-profiles", headers=headers)


def delete_split_model_profile(
    client: TestClient,
    profile_id: str,
    *,
    headers: dict[str, str] | None = None,
):
    llm = client.delete(f"/api/llm-models/{profile_id}", headers=headers)
    if llm.status_code >= 400:
        return llm
    voice = client.delete(f"/api/voice-models/{profile_id}", headers=headers)
    if voice.status_code >= 400:
        return voice
    live2d = client.delete(f"/api/live2d-models/{profile_id}", headers=headers)
    if live2d.status_code >= 400:
        return live2d
    return client.get("/api/model-profiles", headers=headers)


def set_character_model_binding(
    client: TestClient,
    role_name: str,
    profile_id: str,
    *,
    headers: dict[str, str] | None = None,
):
    return client.patch(
        f"/api/character-profiles/{role_name}",
        headers=headers,
        json={"model_profile_id": profile_id},
    )


def clear_character_model_binding(
    client: TestClient,
    role_name: str,
    *,
    headers: dict[str, str] | None = None,
):
    return client.patch(
        f"/api/character-profiles/{role_name}",
        headers=headers,
        json={"clear_model_profile_binding": True},
    )


class AppApiTests(unittest.TestCase):
    def test_health_and_channel_endpoints_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                health = client.get("/api/health")
                definitions = client.get("/api/channels/definitions")
                config = client.get("/api/channels/config")
                roles = client.get("/api/roles")

            self.assertEqual(200, health.status_code)
            self.assertEqual("ok", health.json()["status"])
            self.assertEqual("default", health.json()["current_session"])
            self.assertEqual("default", health.json()["current_role"])
            self.assertEqual(200, definitions.status_code)
            self.assertEqual(
                ["console", "telegram", "discord", "qq"],
                [item["name"] for item in definitions.json()],
            )
            self.assertEqual(200, config.status_code)
            self.assertIn("telegram", config.json())
            self.assertEqual(200, roles.status_code)
            self.assertEqual(["default"], [item["name"] for item in roles.json()])

    def test_channel_config_api_redacts_gateway_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / ".echobot" / "channels.json"
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=config_path,
                context_builder=build_test_context,
            )

            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": False,
                    "allow_from": ["12345"],
                    "mirror_to_stage": True,
                    "stage_session_name": "stage",
                    "bot_token": "telegram-secret-token",
                    "proxy": "socks5://127.0.0.1:1080",
                    "reply_to_message": True,
                    "drop_pending_updates": False,
                },
                "discord": {
                    "enabled": False,
                    "allow_from": ["discord-user"],
                    "mirror_to_stage": True,
                    "stage_session_name": "stage",
                    "bot_token": "discord-secret-token",
                    "webhook_url": "https://discord.com/api/webhooks/1/token",
                    "webhook_secret": "discord-webhook-secret",
                    "application_id": "discord-app-id",
                    "guild_id": "discord-guild-id",
                },
                "qq": {
                    "enabled": False,
                    "allow_from": ["qq-user"],
                    "app_id": "qq-app-id",
                    "client_secret": "qq-client-secret",
                },
            }

            with TestClient(app) as client:
                updated = client.put("/api/channels/config", json=raw_config)
                fetched = client.get("/api/channels/config")

            self.assertEqual(200, updated.status_code)
            self.assertEqual(200, fetched.status_code)
            for payload in [updated.json(), fetched.json()]:
                self.assertNotIn("telegram-secret-token", json.dumps(payload))
                self.assertNotIn("discord-secret-token", json.dumps(payload))
                self.assertNotIn("discord-webhook-secret", json.dumps(payload))
                self.assertNotIn("qq-client-secret", json.dumps(payload))
                self.assertEqual("", payload["telegram"]["bot_token"])
                self.assertTrue(payload["telegram"]["bot_token_configured"])
                self.assertEqual("", payload["discord"]["bot_token"])
                self.assertTrue(payload["discord"]["bot_token_configured"])
                self.assertEqual("", payload["discord"]["webhook_secret"])
                self.assertTrue(payload["discord"]["webhook_secret_configured"])
                self.assertEqual(
                    "https://discord.com/api/webhooks/1/token",
                    payload["discord"]["webhook_url"],
                )
                self.assertEqual("discord-app-id", payload["discord"]["application_id"])
                self.assertEqual("", payload["qq"]["client_secret"])
                self.assertTrue(payload["qq"]["client_secret_configured"])
                self.assertEqual("socks5://127.0.0.1:1080", payload["telegram"]["proxy"])
                self.assertFalse(payload["telegram"]["drop_pending_updates"])
                self.assertEqual("qq-app-id", payload["qq"]["app_id"])

            stored_text = config_path.read_text(encoding="utf-8")
            self.assertIn("telegram-secret-token", stored_text)
            self.assertIn("discord-secret-token", stored_text)
            self.assertIn("discord-webhook-secret", stored_text)
            self.assertIn("qq-client-secret", stored_text)

    def test_channel_config_update_preserves_redacted_gateway_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / ".echobot" / "channels.json"
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=config_path,
                context_builder=build_test_context,
            )

            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": False,
                    "allow_from": ["12345"],
                    "bot_token": "telegram-secret-token",
                    "proxy": "socks5://127.0.0.1:1080",
                    "reply_to_message": True,
                },
                "discord": {
                    "enabled": False,
                    "allow_from": ["discord-user"],
                    "bot_token": "discord-secret-token",
                    "webhook_url": "https://discord.com/api/webhooks/1/token",
                    "webhook_secret": "discord-webhook-secret",
                    "application_id": "discord-app-id",
                    "guild_id": "discord-guild-id",
                },
                "qq": {
                    "enabled": False,
                    "allow_from": ["qq-user"],
                    "app_id": "qq-app-id",
                    "client_secret": "qq-client-secret",
                },
            }

            with TestClient(app) as client:
                client.put("/api/channels/config", json=raw_config)
                redacted = client.get("/api/channels/config").json()
                redacted["telegram"]["proxy"] = "http://proxy.local:8080"
                redacted["telegram"]["drop_pending_updates"] = False
                preserved = client.put("/api/channels/config", json=redacted)

            self.assertEqual(200, preserved.status_code)
            self.assertEqual("", preserved.json()["telegram"]["bot_token"])
            self.assertEqual("", preserved.json()["discord"]["bot_token"])
            self.assertEqual("", preserved.json()["discord"]["webhook_secret"])
            stored_text = config_path.read_text(encoding="utf-8")
            self.assertIn("telegram-secret-token", stored_text)
            self.assertIn("discord-secret-token", stored_text)
            self.assertIn('"drop_pending_updates": false', stored_text)
            self.assertIn("discord-webhook-secret", stored_text)
            self.assertIn("qq-client-secret", stored_text)
            self.assertIn("http://proxy.local:8080", stored_text)

    def test_channel_smoke_checks_validate_config_without_echoing_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / ".echobot" / "channels.json"
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=config_path,
                context_builder=build_test_context,
            )

            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": False,
                    "allow_from": ["12345"],
                    "mirror_to_stage": True,
                    "stage_session_name": "stage",
                    "bot_token": "telegram-secret-token",
                    "proxy": "",
                    "reply_to_message": False,
                },
                "discord": {
                    "enabled": False,
                    "allow_from": ["discord-user"],
                    "mirror_to_stage": True,
                    "stage_session_name": "stage",
                    "bot_token": "discord-secret-token",
                    "webhook_url": "https://discord.com/api/webhooks/1/token",
                    "webhook_secret": "discord-webhook-secret",
                    "application_id": "discord-app-id",
                    "guild_id": "discord-guild-id",
                },
                "qq": {"enabled": False, "allow_from": [], "client_secret": ""},
            }

            with TestClient(app) as client:
                client.put("/api/channels/config", json=raw_config)
                telegram = client.post("/api/channels/telegram/smoke")
                discord = client.post("/api/channels/discord/smoke")
                unknown = client.post("/api/channels/slack/smoke")

            self.assertEqual(200, telegram.status_code)
            self.assertEqual("telegram", telegram.json()["channel"])
            self.assertTrue(telegram.json()["ok"])
            self.assertEqual("configured_disabled", telegram.json()["status"])
            self.assertIn(
                "pending_updates",
                [item["name"] for item in telegram.json()["checks"]],
            )
            self.assertNotIn("telegram-secret-token", json.dumps(telegram.json()))

            self.assertEqual(200, discord.status_code)
            self.assertEqual("discord", discord.json()["channel"])
            self.assertTrue(discord.json()["ok"])
            self.assertEqual("configuration_ready", discord.json()["status"])
            self.assertIn(
                "runtime adapter",
                " ".join(discord.json()["next_steps"]).lower(),
            )
            self.assertNotIn("discord-secret-token", json.dumps(discord.json()))
            self.assertNotIn("discord-webhook-secret", json.dumps(discord.json()))

            self.assertEqual(404, unknown.status_code)

    def test_channel_stage_targets_expose_configured_sessions_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / ".echobot" / "channels.json"
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=config_path,
                context_builder=build_test_context,
            )

            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": False,
                    "allow_from": ["12345"],
                    "mirror_to_stage": True,
                    "stage_session_name": "Telegram Live",
                    "bot_token": "telegram-secret-token",
                    "proxy": "",
                    "reply_to_message": False,
                },
                "discord": {
                    "enabled": False,
                    "allow_from": ["discord-user"],
                    "mirror_to_stage": False,
                    "stage_session_name": "Discord Live",
                    "bot_token": "discord-secret-token",
                    "webhook_url": "",
                    "webhook_secret": "discord-webhook-secret",
                    "application_id": "",
                    "guild_id": "",
                },
                "qq": {"enabled": False, "allow_from": [], "client_secret": ""},
            }

            with TestClient(app) as client:
                updated = client.put("/api/channels/config", json=raw_config)
                targets = client.get("/api/channels/stage-targets")

            self.assertEqual(200, updated.status_code)
            self.assertEqual(200, targets.status_code)
            payload = targets.json()
            self.assertEqual(1, len(payload["targets"]))
            self.assertEqual("telegram", payload["targets"][0]["channel"])
            self.assertEqual("Telegram", payload["targets"][0]["label"])
            self.assertEqual("telegram-live", payload["targets"][0]["session_name"])
            self.assertTrue(payload["targets"][0]["configured"])
            self.assertFalse(payload["targets"][0]["enabled"])
            self.assertFalse(payload["targets"][0]["running"])
            self.assertNotIn("telegram-secret-token", json.dumps(payload))
            self.assertNotIn("discord-secret-token", json.dumps(payload))
            self.assertNotIn("discord-webhook-secret", json.dumps(payload))

    def test_discord_webhook_routes_to_bound_session_and_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with patch(
                "echobot.channels.platforms.discord._post_webhook_message",
                return_value=None,
            ):
                with TestClient(app) as client:
                    client.put(
                        "/api/channels/config",
                        json={
                            "discord": {
                                "enabled": True,
                                "allow_from": ["discord-user"],
                                "mirror_to_stage": True,
                                "stage_session_name": "legacy-discord-stage",
                                "webhook_url": "https://discord.example/webhook",
                                "webhook_secret": "discord-secret",
                            },
                        },
                    )
                    client.post(
                        "/api/sessions",
                        json={
                            "name": "ops-room",
                            "channel_type": "discord",
                            "channel_integration_id": "discord",
                        },
                    )
                    accepted = client.post(
                        "/api/channels/discord/webhook",
                        headers={"X-EchoBot-Discord-Secret": "discord-secret"},
                        json={
                            "channel_id": "channel-1",
                            "user_id": "discord-user",
                            "text": "ping",
                        },
                    )
                    detail = _wait_for_session_messages(client, "ops-room", 2)
                    runtime = app.state.runtime
                    history = runtime.stage_event_broker.history("default", "ops-room")

            self.assertEqual(200, accepted.status_code)
            self.assertTrue(accepted.json()["accepted"])
            self.assertEqual(2, len(detail["history"]))
            self.assertEqual("ping", detail["history"][0]["content"])
            self.assertEqual("pong", detail["history"][1]["content"])
            self.assertEqual(["pong"], [item.text for item in history])

    def test_local_channel_e2e_test_routes_to_bound_session_and_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                client.put(
                    "/api/channels/config",
                    json={
                        "discord": {
                            "enabled": False,
                            "allow_from": ["discord-user"],
                            "mirror_to_stage": True,
                            "stage_session_name": "legacy-discord-stage",
                        },
                    },
                )
                client.post(
                    "/api/sessions",
                    json={
                        "name": "Ops Room",
                        "channel_type": "discord",
                        "channel_integration_id": "discord",
                    },
                )
                rejected = client.post(
                    "/api/channels/discord/local-test-message",
                    json={
                        "chat_id": "channel-1",
                        "sender_id": "other-user",
                        "text": "ping",
                    },
                )
                accepted = client.post(
                    "/api/channels/discord/local-test-message",
                    json={
                        "chat_id": "channel-1",
                        "sender_id": "discord-user",
                        "text": "ping",
                    },
                )
                detail = _wait_for_session_messages(client, "ops-room", 2)
                runtime = app.state.runtime
                history = runtime.stage_event_broker.history("default", "ops-room")

            self.assertEqual(403, rejected.status_code)
            self.assertEqual(200, accepted.status_code)
            self.assertTrue(accepted.json()["accepted"])
            self.assertEqual("discord", accepted.json()["channel"])
            self.assertFalse(accepted.json()["external_delivery"])
            self.assertEqual(2, len(detail["history"]))
            self.assertEqual("ping", detail["history"][0]["content"])
            self.assertEqual("pong", detail["history"][1]["content"])
            self.assertEqual(["pong"], [item.text for item in history])
            self.assertEqual(["discord"], [item.source for item in history])

    def test_channel_smoke_requires_admin_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "ECHOBOT_ADMIN_ALLOWLIST": "admin@example.test",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

            admin_headers = {DEFAULT_TRUSTED_USER_HEADER: "admin@example.test"}
            user_headers = {DEFAULT_TRUSTED_USER_HEADER: "user@example.test"}

            with TestClient(app) as client:
                blocked = client.post(
                    "/api/channels/telegram/smoke",
                    headers=user_headers,
                )
                allowed = client.post(
                    "/api/channels/telegram/smoke",
                    headers=admin_headers,
                )

            self.assertEqual(403, blocked.status_code)
            self.assertEqual("Admin access is required", blocked.json()["detail"])
            self.assertEqual(200, allowed.status_code)

    def test_gateway_response_is_mirrored_to_stage_when_channel_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / ".echobot" / "channels.json"
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=config_path,
                context_builder=build_test_context,
            )

            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": False,
                    "allow_from": ["12345"],
                    "mirror_to_stage": True,
                    "stage_session_name": "front",
                    "bot_token": "telegram-secret-token",
                    "proxy": "",
                    "reply_to_message": False,
                },
                "discord": {"enabled": False, "allow_from": []},
                "qq": {"enabled": False, "allow_from": []},
            }

            with TestClient(app) as client:
                client.put("/api/channels/config", json=raw_config)
                runtime = app.state.runtime
                context = runtime.context
                assert context is not None
                outbound = ChannelAddress(
                    channel="telegram",
                    chat_id="12345",
                )
                awaitable = runtime.publish_gateway_stage_event(
                    "telegram__12345__session",
                    SimpleNamespace(
                        address=outbound,
                        text="stage mirror ok",
                        content="stage mirror ok",
                    ),
                )
                asyncio.run(awaitable)
                events = runtime.stage_event_broker.history(
                    "default",
                    "telegram__12345__session",
                )

            self.assertEqual(1, len(events))
            self.assertEqual("assistant_final", events[0].kind)
            self.assertEqual("stage mirror ok", events[0].text)
            self.assertEqual("telegram", events[0].source)
            self.assertEqual("telegram__12345__session", events[0].metadata["gateway_session_name"])

    def test_user_scoped_gateway_stage_event_is_visible_without_trusted_header_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / ".echobot" / "channels.json"
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=config_path,
                context_builder=build_test_context,
            )
            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": False,
                    "allow_from": ["12345"],
                    "mirror_to_stage": True,
                    "stage_session_name": "front",
                    "bot_token": "telegram-secret-token",
                    "proxy": "",
                    "reply_to_message": False,
                },
                "discord": {"enabled": False, "allow_from": []},
                "qq": {"enabled": False, "allow_from": []},
            }

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "false",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "false",
                },
                clear=False,
            ):
                with TestClient(app) as client:
                    client.put("/api/channels/config", json=raw_config)
                    runtime = app.state.runtime
                    user_runtime = asyncio.run(runtime.for_user("viewer@example.com"))
                    outbound = ChannelAddress(
                        channel="telegram",
                        chat_id="12345",
                        user_id="viewer@example.com",
                    )
                    asyncio.run(
                        user_runtime.publish_gateway_stage_event(
                            "front",
                            SimpleNamespace(
                                address=outbound,
                                text="visible local stage",
                                content="visible local stage",
                            ),
                        )
                    )
                    default_events = runtime.stage_event_broker.history(
                        "default",
                        "front",
                    )
                    scoped_events = runtime.stage_event_broker.history(
                        user_storage_key("viewer@example.com"),
                        "front",
                    )

            self.assertEqual(1, len(default_events))
            self.assertEqual(1, len(scoped_events))
            self.assertEqual("visible local stage", default_events[0].text)
            self.assertEqual("visible local stage", scoped_events[0].text)

    def test_user_scoped_gateway_stage_event_stays_scoped_when_trusted_header_mode_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_path = workspace / ".echobot" / "channels.json"
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=config_path,
                context_builder=build_test_context,
            )
            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": False,
                    "allow_from": ["12345"],
                    "mirror_to_stage": True,
                    "stage_session_name": "front",
                    "bot_token": "telegram-secret-token",
                    "proxy": "",
                    "reply_to_message": False,
                },
                "discord": {"enabled": False, "allow_from": []},
                "qq": {"enabled": False, "allow_from": []},
            }

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                },
                clear=False,
            ):
                with TestClient(app) as client:
                    client.put("/api/channels/config", json=raw_config)
                    runtime = app.state.runtime
                    user_runtime = asyncio.run(runtime.for_user("viewer@example.com"))
                    outbound = ChannelAddress(
                        channel="telegram",
                        chat_id="12345",
                        user_id="viewer@example.com",
                    )
                    asyncio.run(
                        user_runtime.publish_gateway_stage_event(
                            "front",
                            SimpleNamespace(
                                address=outbound,
                                text="scoped only",
                                content="scoped only",
                            ),
                        )
                    )
                    default_events = runtime.stage_event_broker.history(
                        "default",
                        "front",
                    )
                    scoped_events = runtime.stage_event_broker.history(
                        user_storage_key("viewer@example.com"),
                        "front",
                    )

            self.assertEqual([], default_events)
            self.assertEqual(1, len(scoped_events))
            self.assertEqual("scoped only", scoped_events[0].text)

    def test_trusted_user_header_is_required_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

            with TestClient(app) as client:
                missing = client.get("/api/health")
                invalid = client.get(
                    "/api/health",
                    headers={DEFAULT_TRUSTED_USER_HEADER: "alpha/../beta"},
                )
                authorized = client.get(
                    "/api/health",
                    headers={DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"},
                )

            self.assertEqual(401, missing.status_code)
            self.assertEqual("Trusted user header is required", missing.json()["detail"])
            self.assertEqual(401, invalid.status_code)
            self.assertEqual("Trusted user header is invalid", invalid.json()["detail"])
            self.assertEqual(200, authorized.status_code)
            self.assertEqual("alpha@example.test", authorized.json()["trusted_user"])

    def test_admin_allowlist_blocks_mutating_admin_apis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "ECHOBOT_ADMIN_ALLOWLIST": "admin@example.test",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

            admin_headers = {DEFAULT_TRUSTED_USER_HEADER: "admin@example.test"}
            user_headers = {DEFAULT_TRUSTED_USER_HEADER: "user@example.test"}
            raw_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {"enabled": False, "allow_from": [], "bot_token": "secret"},
                "qq": {"enabled": False, "allow_from": [], "client_secret": "secret"},
            }

            with TestClient(app) as client:
                readonly = client.get("/api/channels/config", headers=user_headers)
                blocked_channel_update = client.put(
                    "/api/channels/config",
                    headers=user_headers,
                    json=raw_config,
                )
                blocked_runtime_update = client.patch(
                    "/api/web/runtime",
                    headers=user_headers,
                    json={"file_write_enabled": True},
                )
                blocked_heartbeat_update = client.put(
                    "/api/heartbeat",
                    headers=user_headers,
                    json={"content": "# HEARTBEAT.md\n\n- [ ] blocked\n"},
                )
                allowed_channel_update = client.put(
                    "/api/channels/config",
                    headers=admin_headers,
                    json=raw_config,
                )

            self.assertEqual(200, readonly.status_code)
            self.assertEqual(403, blocked_channel_update.status_code)
            self.assertEqual("Admin access is required", blocked_channel_update.json()["detail"])
            self.assertEqual(403, blocked_runtime_update.status_code)
            self.assertEqual(403, blocked_heartbeat_update.status_code)
            self.assertEqual(200, allowed_channel_update.status_code)

    def test_trusted_user_header_protects_product_routes_and_api_docs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

            protected_routes = [
                "/stage?session_name=demo",
                "/console",
                "/messenger",
                "/admin",
                "/admin/guide",
                "/admin/structure",
                "/admin/channels",
                "/admin/characters",
                "/admin/openwebui",
                "/admin/models",
                "/admin/voice-models",
                "/admin/live2d",
                "/docs",
                "/redoc",
                "/openapi.json",
            ]
            headers = {DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"}

            with TestClient(app) as client:
                missing = [client.get(path) for path in protected_routes]
                authorized = [client.get(path, headers=headers) for path in protected_routes]

            self.assertTrue(all(response.status_code == 401 for response in missing))
            self.assertTrue(all(response.status_code == 200 for response in authorized))
            self.assertIn('id="stage-root"', authorized[0].text)
            self.assertIn("data-display-mode-switcher", authorized[0].text)
            self.assertIn("data-language-switcher", authorized[1].text)
            self.assertIn("data-display-mode-switcher", authorized[1].text)
            self.assertIn('id="structure-root"', authorized[5].text)
            self.assertIn('id="messenger-root"', authorized[2].text)
            self.assertIn("data-display-mode-switcher", authorized[2].text)
            self.assertIn('id="admin-root"', authorized[3].text)
            self.assertIn("data-display-mode-switcher", authorized[3].text)
            self.assertIn('id="guide-root"', authorized[4].text)
            self.assertIn("data-display-mode-switcher", authorized[4].text)
            self.assertIn('id="channels-root"', authorized[6].text)
            self.assertIn("data-display-mode-switcher", authorized[6].text)
            self.assertIn('id="characters-root"', authorized[7].text)
            self.assertIn("data-display-mode-switcher", authorized[7].text)
            self.assertIn('id="openwebui-root"', authorized[8].text)
            self.assertIn("data-display-mode-switcher", authorized[8].text)
            self.assertIn('id="models-root"', authorized[9].text)
            self.assertIn("data-display-mode-switcher", authorized[9].text)
            self.assertIn('id="voice-models-root"', authorized[10].text)
            self.assertIn("data-display-mode-switcher", authorized[10].text)
            self.assertIn('id="live2d-root"', authorized[11].text)
            self.assertIn("data-display-mode-switcher", authorized[11].text)

    def test_web_page_route_registry_serves_known_shells(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            expected_markers = {
                "/web": 'class="page-shell"',
                "/console": 'class="page-shell"',
                "/stage": 'id="stage-root"',
                "/messenger": 'id="messenger-root"',
                "/admin": 'id="admin-root"',
                "/admin/guide": 'id="guide-root"',
                "/admin/structure": 'id="structure-root"',
                "/admin/sessions": 'id="sessions-root"',
                "/admin/channels": 'id="channels-root"',
                "/admin/characters": 'id="characters-root"',
                "/admin/openwebui": 'id="openwebui-root"',
                "/admin/models": 'id="models-root"',
                "/admin/voice-models": 'id="voice-models-root"',
                "/admin/live2d": 'id="live2d-root"',
            }

            with TestClient(app) as client:
                route_paths = [route.path for route in WEB_PAGE_ROUTES]
                responses = {
                    path: client.get(path)
                    for path in route_paths
                }

            self.assertEqual(list(expected_markers), route_paths)
            self.assertTrue(
                all(response.status_code == 200 for response in responses.values()),
            )
            for path, marker in expected_markers.items():
                self.assertIn(marker, responses[path].text)

    def test_openwebui_bridge_uses_bearer_token_and_narrow_tool_spec(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN": "bridge-secret",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

                with TestClient(app) as client:
                    status_missing_user = client.get("/api/openwebui/status")
                    status_authorized = client.get(
                        "/api/openwebui/status",
                        headers={DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"},
                    )
                    missing_token = client.get("/api/openwebui/tools/openapi.json")
                    invalid_token = client.get(
                        "/api/openwebui/tools/openapi.json",
                        headers={"Authorization": "Bearer wrong-secret"},
                    )
                    tool_spec = client.get(
                        "/api/openwebui/tools/openapi.json",
                        headers={"Authorization": "Bearer bridge-secret"},
                    )

            self.assertEqual(401, status_missing_user.status_code)
            self.assertEqual(200, status_authorized.status_code)
            self.assertFalse(status_authorized.json()["operator_agent_enabled"])
            self.assertEqual(401, missing_token.status_code)
            self.assertEqual("Open WebUI bridge token is invalid", missing_token.json()["detail"])
            self.assertEqual(401, invalid_token.status_code)
            self.assertEqual(200, tool_spec.status_code)
            self.assertEqual(
                {
                    "/api/openwebui/stage/events",
                    "/api/openwebui/chat",
                    "/api/openwebui/sessions",
                },
                set(tool_spec.json()["paths"].keys()),
            )
            self.assertNotIn("/openapi.json", tool_spec.json()["paths"])
            self.assertNotIn("/api/health", tool_spec.json()["paths"])
            paths = tool_spec.json()["paths"]
            stage_schema = paths["/api/openwebui/stage/events"]["post"]["requestBody"]["content"]["application/json"]["schema"]
            chat_schema = paths["/api/openwebui/chat"]["post"]["requestBody"]["content"]["application/json"]["schema"]
            sessions_params = paths["/api/openwebui/sessions"]["get"]["parameters"]
            self.assertIn("target_user_id", stage_schema["required"])
            self.assertIn("emotion", stage_schema["properties"])
            self.assertIn("expression", stage_schema["properties"])
            self.assertIn("motion", stage_schema["properties"])
            self.assertIn("target_user_id", chat_schema["required"])
            self.assertTrue(sessions_params[0]["required"])

    def test_model_profiles_are_user_scoped_and_apply_to_console_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "LLM_API_KEY": "test-key",
                    "LLM_MODEL": "base-chat-model",
                    "LLM_BASE_URL": "http://base-llm.test/v1",
                    "ECHOBOT_TTS_PROVIDER": "edge",
                    "ECHOBOT_ASR_PROVIDER": "sherpa-sense-voice",
                    "ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD": "false",
                    "ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD": "false",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                )

                alpha_headers = {DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"}
                beta_headers = {DEFAULT_TRUSTED_USER_HEADER: "beta@example.test"}
                alpha_storage = (
                    workspace
                    / ".echobot"
                    / "users"
                    / user_storage_key("alpha@example.test")
                )

                with TestClient(app) as client:
                    initial = client.get("/api/model-profiles", headers=alpha_headers)
                    base_config = client.get("/api/web/config", headers=alpha_headers)
                    live2d_key = base_config.json()["live2d"]["models"][0]["selection_key"]
                    updated = update_split_model_profile(
                        client,
                        "b",
                        headers=alpha_headers,
                        label="Streamer B",
                        chat={
                            "provider": "private-litellm",
                            "model": "profile-chat-model",
                            "base_url": "http://provider.test/v1",
                            "temperature": 0.4,
                            "max_tokens": 2048,
                            "api_key": "profile-chat-key",
                        },
                        tts={
                            "provider": "openai-compatible",
                            "model": "tts-profile-model",
                            "base_url": "http://tts.test/v1",
                            "voice": "voice-profile",
                            "api_key": "profile-tts-key",
                        },
                        asr={
                            "provider": "openai-transcriptions",
                            "model": "asr-profile-model",
                            "base_url": "http://asr.test/v1",
                            "language": "zh",
                            "api_key": "profile-asr-key",
                        },
                        live2d={
                            "selection_key": live2d_key,
                        },
                    )
                    created = create_split_model_profile(
                        client,
                        headers=alpha_headers,
                        name="Streamer Custom",
                        source_profile_id="b",
                    )
                    duplicate = create_split_model_profile(
                        client,
                        headers=alpha_headers,
                        name="Streamer Custom",
                    )
                    duplicate_secret_update = update_split_model_profile(
                        client,
                        duplicate.json()["profile_id"],
                        headers=alpha_headers,
                        chat={
                            "provider": "openai-compatible",
                            "model": "duplicate-chat-model",
                            "base_url": "http://duplicate-provider.test/v1",
                            "api_key": "duplicate-chat-key",
                        },
                    )
                    activated = activate_split_model_profile(
                        client,
                        created.json()["profile_id"],
                        headers=alpha_headers,
                    )
                    delete_active = delete_split_model_profile(
                        client,
                        created.json()["profile_id"],
                        headers=alpha_headers,
                    )
                    deleted_duplicate = delete_split_model_profile(
                        client,
                        duplicate.json()["profile_id"],
                        headers=alpha_headers,
                    )
                    console_config = client.get("/api/web/config", headers=alpha_headers)
                    beta_profiles = client.get("/api/model-profiles", headers=beta_headers)
                    runtime = app.state.runtime
                    alpha_runtime = next(
                        item
                        for item in runtime.user_runtime_factory.cached_runtimes()
                        if item.user_id == "alpha@example.test"
                    )
                    alpha_provider_model = (
                        alpha_runtime.context.agent.provider.settings.model
                    )
                    alpha_provider_base_url = (
                        alpha_runtime.context.agent.provider.settings.base_url
                    )
                    alpha_provider_api_key = (
                        alpha_runtime.context.agent.provider.settings.api_key
                    )
                    parent_applier_ready = runtime.runtime_profile_applier is not None
                    user_applier_ready = alpha_runtime.runtime_profile_applier is not None

            self.assertEqual(200, initial.status_code)
            self.assertEqual("a", initial.json()["active_profile_id"])
            self.assertEqual(
                ["a", "b", "c", "d", "e"],
                [item["profile_id"] for item in initial.json()["profiles"]],
            )

            self.assertEqual(200, updated.status_code)
            self.assertEqual("Streamer B", updated.json()["label"])
            self.assertEqual("profile-chat-model", updated.json()["chat"]["model"])
            self.assertNotIn("api_key", updated.json()["chat"])
            self.assertTrue(updated.json()["chat"]["api_key_configured"])
            self.assertEqual("profile", updated.json()["chat"]["api_key_source"])
            self.assertTrue(updated.json()["tts"]["api_key_configured"])
            self.assertTrue(updated.json()["asr"]["api_key_configured"])

            self.assertEqual(200, created.status_code)
            self.assertEqual("streamer-custom", created.json()["profile_id"])
            self.assertEqual("Streamer Custom", created.json()["label"])
            self.assertEqual("profile-chat-model", created.json()["chat"]["model"])
            self.assertEqual("http://provider.test/v1", created.json()["chat"]["base_url"])
            self.assertNotIn("api_key", created.json()["chat"])
            self.assertEqual("environment", created.json()["chat"]["api_key_source"])
            self.assertFalse(created.json()["tts"]["api_key_configured"])
            self.assertFalse(created.json()["asr"]["api_key_configured"])

            self.assertEqual(200, duplicate.status_code)
            self.assertEqual("streamer-custom-2", duplicate.json()["profile_id"])
            self.assertEqual(200, duplicate_secret_update.status_code)
            self.assertTrue(
                duplicate_secret_update.json()["chat"]["api_key_configured"],
            )

            self.assertEqual(200, activated.status_code)
            self.assertEqual("streamer-custom", activated.json()["active_profile_id"])
            self.assertEqual(400, delete_active.status_code)
            self.assertIn("Active model profile", delete_active.json()["detail"])
            self.assertEqual(200, deleted_duplicate.status_code)
            self.assertEqual("streamer-custom", deleted_duplicate.json()["active_profile_id"])
            self.assertNotIn(
                "streamer-custom-2",
                [item["profile_id"] for item in deleted_duplicate.json()["profiles"]],
            )

            self.assertEqual(200, console_config.status_code)
            console_profiles = console_config.json()["model_profiles"]
            self.assertEqual("streamer-custom", console_profiles["active_profile_id"])
            active_profile = next(
                item
                for item in console_profiles["profiles"]
                if item["profile_id"] == "streamer-custom"
            )
            self.assertEqual("profile-chat-model", active_profile["chat"]["model"])
            self.assertEqual(live2d_key, active_profile["live2d"]["selection_key"])
            self.assertEqual("openai-compatible", console_config.json()["tts"]["default_provider"])
            self.assertEqual(
                "openai-transcriptions",
                console_config.json()["asr"]["selected_asr_provider"],
            )

            stored_text = (alpha_storage / "model_profiles.json").read_text(
                encoding="utf-8",
            )
            self.assertIn("profile-chat-model", stored_text)
            self.assertIn("streamer-custom", stored_text)
            self.assertNotIn("streamer-custom-2", stored_text)
            self.assertNotIn("profile-chat-key", stored_text)
            self.assertNotIn("profile-tts-key", stored_text)
            self.assertNotIn("profile-asr-key", stored_text)
            self.assertNotIn("duplicate-chat-key", stored_text)
            self.assertNotIn("api_key", stored_text)
            llm_secret_text = (alpha_storage / "llm_model_secrets.json").read_text(
                encoding="utf-8",
            )
            voice_secret_text = (alpha_storage / "voice_profile_secrets.json").read_text(
                encoding="utf-8",
            )
            self.assertIn("profile-chat-key", llm_secret_text)
            self.assertIn("profile-tts-key", voice_secret_text)
            self.assertIn("profile-asr-key", voice_secret_text)
            self.assertNotIn("duplicate-chat-key", llm_secret_text)

            self.assertEqual("profile-chat-model", alpha_provider_model)
            self.assertEqual("http://provider.test/v1", alpha_provider_base_url)
            self.assertEqual("test-key", alpha_provider_api_key)
            self.assertTrue(parent_applier_ready)
            self.assertTrue(user_applier_ready)

            self.assertEqual(200, beta_profiles.status_code)
            self.assertEqual("a", beta_profiles.json()["active_profile_id"])
            self.assertNotIn(
                "streamer-custom",
                [item["profile_id"] for item in beta_profiles.json()["profiles"]],
            )
            beta_b_profile = next(
                item
                for item in beta_profiles.json()["profiles"]
                if item["profile_id"] == "b"
            )
            self.assertEqual("Profile B", beta_b_profile["label"])

    def test_new_user_model_profiles_seed_from_parent_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "LLM_API_KEY": "base-key",
                    "LLM_MODEL": "base-chat-model",
                    "LLM_BASE_URL": "http://base-llm.test/v1",
                    "ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD": "false",
                    "ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD": "false",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

                with TestClient(app) as client:
                    runtime = app.state.runtime
                    runtime.model_profile_service.update_profile(
                        "b",
                        {
                            "label": "Parent GB10",
                            "chat": {
                                "model": "parent-gb10-model",
                                "base_url": "http://parent-gb10.test/v1",
                                "api_key": "parent-gb10-key",
                            },
                        },
                    )
                    runtime.model_profile_service.activate_profile("b")

                    headers = {DEFAULT_TRUSTED_USER_HEADER: "fresh@example.test"}
                    profiles = client.get("/api/model-profiles", headers=headers)
                    config = client.get("/api/web/config", headers=headers)
                    runtime = app.state.runtime
                    user_runtime = next(
                        item
                        for item in runtime.user_runtime_factory.cached_runtimes()
                        if item.user_id == "fresh@example.test"
                    )

            self.assertEqual(200, profiles.status_code)
            self.assertEqual("b", profiles.json()["active_profile_id"])
            seeded_profile = next(
                item
                for item in profiles.json()["profiles"]
                if item["profile_id"] == "b"
            )
            self.assertEqual("Parent GB10", seeded_profile["label"])
            self.assertEqual("parent-gb10-model", seeded_profile["chat"]["model"])
            self.assertEqual("profile", seeded_profile["chat"]["api_key_source"])

            self.assertEqual(200, config.status_code)
            self.assertEqual("b", config.json()["model_profiles"]["active_profile_id"])
            provider_settings = user_runtime.context.agent.provider.settings
            self.assertEqual("parent-gb10-model", provider_settings.model)
            self.assertEqual("http://parent-gb10.test/v1", provider_settings.base_url)
            self.assertEqual("parent-gb10-key", provider_settings.api_key)

    def test_legacy_model_profile_write_endpoints_are_retired(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                responses = [
                    client.post("/api/model-profiles", json={"label": "Legacy"}),
                    client.patch(
                        "/api/model-profiles/b",
                        json={"chat": {"model": "legacy-write"}},
                    ),
                    client.post("/api/model-profiles/b/activate"),
                    client.delete("/api/model-profiles/b"),
                    client.put(
                        "/api/model-profiles/role-bindings/default",
                        json={"profile_id": "b"},
                    ),
                    client.delete("/api/model-profiles/role-bindings/default"),
                ]

            for response in responses:
                self.assertEqual(410, response.status_code)
                self.assertEqual("true", response.headers.get("Deprecation"))
                self.assertEqual(
                    "model-profiles",
                    response.headers.get("X-EchoBot-Compatibility-Path"),
                )
                self.assertEqual(
                    "domain-runtime-profiles",
                    response.headers.get("X-EchoBot-Replacement-Path"),
                )

    def test_model_profile_role_bindings_apply_on_role_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "LLM_API_KEY": "base-key",
                    "LLM_MODEL": "base-chat-model",
                    "LLM_BASE_URL": "http://base-llm.test/v1",
                    "ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD": "false",
                    "ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD": "false",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

                alpha_headers = {DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"}
                beta_headers = {DEFAULT_TRUSTED_USER_HEADER: "beta@example.test"}
                alpha_storage = (
                    workspace
                    / ".echobot"
                    / "users"
                    / user_storage_key("alpha@example.test")
                )

                with TestClient(app) as client:
                    updated_profile = update_split_model_profile(
                        client,
                        "b",
                        headers=alpha_headers,
                        label="Helper Voice",
                        chat={
                            "provider": "private-litellm",
                            "model": "role-bound-chat-model",
                            "base_url": "http://role-bound.test/v1",
                            "api_key": "role-bound-key",
                        },
                    )
                    unknown_role = set_character_model_binding(
                        client,
                        "missing-role",
                        "b",
                        headers=alpha_headers,
                    )
                    created_role = client.post(
                        "/api/roles",
                        headers=alpha_headers,
                        json={
                            "name": "Helper Cat",
                            "prompt": "# Helper Cat\n\nStay concise.",
                        },
                    )
                    unknown_profile = set_character_model_binding(
                        client,
                        "helper-cat",
                        "missing-profile",
                        headers=alpha_headers,
                    )
                    bound = set_character_model_binding(
                        client,
                        "helper-cat",
                        "b",
                        headers=alpha_headers,
                    )
                    binding_list = client.get(
                        "/api/model-profiles/role-bindings",
                        headers=alpha_headers,
                    )
                    beta_profiles = client.get(
                        "/api/model-profiles",
                        headers=beta_headers,
                    )
                    switched = client.put(
                        "/api/sessions/default/role",
                        headers=alpha_headers,
                        json={"role_name": "helper-cat"},
                    )
                    console_config = client.get(
                        "/api/web/config",
                        headers=alpha_headers,
                    )
                    runtime = app.state.runtime
                    alpha_runtime = next(
                        item
                        for item in runtime.user_runtime_factory.cached_runtimes()
                        if item.user_id == "alpha@example.test"
                    )
                    alpha_provider_model = (
                        alpha_runtime.context.agent.provider.settings.model
                    )
                    alpha_provider_base_url = (
                        alpha_runtime.context.agent.provider.settings.base_url
                    )
                    alpha_provider_api_key = (
                        alpha_runtime.context.agent.provider.settings.api_key
                    )
                    activated_default = activate_split_model_profile(
                        client,
                        "a",
                        headers=alpha_headers,
                    )
                    deleted_bound_profile = delete_split_model_profile(
                        client,
                        "b",
                        headers=alpha_headers,
                    )
                    after_delete = client.get(
                        "/api/model-profiles",
                        headers=alpha_headers,
                    )

            self.assertEqual(200, updated_profile.status_code)
            self.assertEqual("role-bound-chat-model", updated_profile.json()["chat"]["model"])

            self.assertEqual(404, unknown_role.status_code)
            self.assertIn("Unknown role", unknown_role.json()["detail"])

            self.assertEqual(200, created_role.status_code)
            self.assertEqual("helper-cat", created_role.json()["name"])

            self.assertEqual(404, unknown_profile.status_code)
            self.assertIn("Unknown model profile", unknown_profile.json()["detail"])

            self.assertEqual(200, bound.status_code)
            self.assertEqual("b", bound.json()["model_profile_id"])

            self.assertEqual(200, binding_list.status_code)
            self.assertEqual({"helper-cat": "b"}, binding_list.json())

            self.assertEqual(200, beta_profiles.status_code)
            self.assertEqual({}, beta_profiles.json()["role_bindings"])

            self.assertEqual(200, switched.status_code)
            self.assertEqual("helper-cat", switched.json()["role_name"])

            self.assertEqual(200, console_config.status_code)
            self.assertEqual(
                "b",
                console_config.json()["model_profiles"]["active_profile_id"],
            )
            self.assertEqual(
                {"helper-cat": "b"},
                console_config.json()["model_profiles"]["role_bindings"],
            )

            self.assertEqual("role-bound-chat-model", alpha_provider_model)
            self.assertEqual("http://role-bound.test/v1", alpha_provider_base_url)
            self.assertEqual("role-bound-key", alpha_provider_api_key)

            self.assertEqual(200, activated_default.status_code)
            self.assertEqual("a", activated_default.json()["active_profile_id"])

            self.assertEqual(200, deleted_bound_profile.status_code)
            self.assertNotIn(
                "b",
                [item["profile_id"] for item in deleted_bound_profile.json()["profiles"]],
            )
            self.assertNotIn(
                "helper-cat",
                after_delete.json()["role_bindings"],
            )
            self.assertNotIn(
                "b",
                [item["profile_id"] for item in after_delete.json()["profiles"]],
            )
            stored_text = (alpha_storage / "model_profiles.json").read_text(
                encoding="utf-8",
            )
            stored_payload = json.loads(stored_text)
            self.assertNotIn("b", stored_payload["profiles"])
            self.assertNotIn("role-bound-key", stored_text)

    def test_character_owned_model_profile_binding_projects_without_legacy_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                updated_profile = update_split_model_profile(
                    client,
                    "b",
                    label="Migrated Binding LLM",
                    chat={
                        "provider": "private-litellm",
                        "model": "migrated-binding-model",
                        "base_url": "http://migrated-binding.test/v1",
                        "api_key": "migrated-binding-key",
                    },
                )
                created_role = client.post(
                    "/api/roles",
                    json={
                        "name": "Migrated Host",
                        "prompt": "# Migrated Host\n\nUse migrated binding.",
                    },
                )
                runtime = app.state.runtime
                runtime.character_profile_settings_service.set_model_profile_binding(
                    "migrated-host",
                    "b",
                )
                legacy_payload = runtime.model_profile_service.list_profiles()
                listed_profiles = client.get("/api/model-profiles")
                role_bindings = client.get("/api/model-profiles/role-bindings")
                switched = client.put(
                    "/api/sessions/default/role",
                    json={"role_name": "migrated-host"},
                )
                web_config = client.get("/api/web/config")
                runtime_context = client.get("/api/sessions/default/runtime-context")
                stage_context = client.get("/api/stage/context?session_name=default")
                provider_settings = runtime.context.agent.provider.settings

            self.assertEqual(200, updated_profile.status_code)
            self.assertEqual(200, created_role.status_code)
            self.assertEqual({}, legacy_payload["role_bindings"])

            self.assertEqual(200, listed_profiles.status_code)
            self.assertEqual(
                {"migrated-host": "b"},
                listed_profiles.json()["role_bindings"],
            )
            self.assertEqual(200, role_bindings.status_code)
            self.assertEqual({"migrated-host": "b"}, role_bindings.json())

            self.assertEqual(200, switched.status_code)
            self.assertEqual("migrated-host", switched.json()["role_name"])
            self.assertEqual(200, web_config.status_code)
            self.assertEqual(
                {"migrated-host": "b"},
                web_config.json()["model_profiles"]["role_bindings"],
            )
            self.assertEqual(200, runtime_context.status_code)
            self.assertEqual(
                "b",
                runtime_context.json()["character"]["model_profile_id"],
            )
            self.assertEqual(
                "b",
                runtime_context.json()["character"]["effective_model_profile_id"],
            )
            self.assertEqual(
                "migrated-binding-model",
                runtime_context.json()["llm_model"]["model"],
            )
            self.assertEqual(200, stage_context.status_code)
            self.assertEqual("b", stage_context.json()["model_profile_id"])
            self.assertEqual("role_binding", stage_context.json()["model_profile_source"])
            self.assertEqual("migrated-binding-model", provider_settings.model)
            self.assertEqual("migrated-binding-key", provider_settings.api_key)

    def test_stage_context_exposes_current_role_and_safe_model_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "LLM_API_KEY": "base-key",
                    "LLM_MODEL": "base-chat-model",
                    "LLM_BASE_URL": "http://base-llm.test/v1",
                    "ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD": "false",
                    "ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD": "false",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

                alpha_headers = {DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"}
                beta_headers = {DEFAULT_TRUSTED_USER_HEADER: "beta@example.test"}

                with TestClient(app) as client:
                    active_context = client.get(
                        "/api/stage/context?session_name=demo",
                        headers=alpha_headers,
                    )
                    updated_profile = update_split_model_profile(
                        client,
                        "b",
                        headers=alpha_headers,
                        label="Stage Voice",
                        chat={
                            "provider": "private-litellm",
                            "model": "stage-chat-model",
                            "base_url": "http://stage-model.test/v1",
                            "api_key": "stage-profile-secret",
                        },
                    )
                    created_role = client.post(
                        "/api/roles",
                        headers=alpha_headers,
                        json={
                            "name": "Stage Host",
                            "prompt": "# Stage Host\n\nSpeak clearly.",
                        },
                    )
                    bound = set_character_model_binding(
                        client,
                        "stage-host",
                        "b",
                        headers=alpha_headers,
                    )
                    switched = client.put(
                        "/api/sessions/demo/role",
                        headers=alpha_headers,
                        json={"role_name": "stage-host"},
                    )
                    bound_context = client.get(
                        "/api/stage/context?session_name=demo",
                        headers=alpha_headers,
                    )
                    beta_context = client.get(
                        "/api/stage/context?session_name=demo",
                        headers=beta_headers,
                    )

            self.assertEqual(200, active_context.status_code)
            self.assertEqual("demo", active_context.json()["session_name"])
            self.assertEqual("default", active_context.json()["role_name"])
            self.assertEqual("a", active_context.json()["model_profile_id"])
            self.assertEqual("Profile A", active_context.json()["model_profile_label"])
            self.assertEqual("active", active_context.json()["model_profile_source"])

            self.assertEqual(200, updated_profile.status_code)
            self.assertNotIn("api_key", updated_profile.json()["chat"])
            self.assertEqual(200, created_role.status_code)
            self.assertEqual(200, bound.status_code)
            self.assertEqual(200, switched.status_code)

            self.assertEqual(200, bound_context.status_code)
            self.assertEqual("demo", bound_context.json()["session_name"])
            self.assertEqual("stage-host", bound_context.json()["role_name"])
            self.assertEqual("b", bound_context.json()["model_profile_id"])
            self.assertEqual("Stage Voice", bound_context.json()["model_profile_label"])
            self.assertEqual("role_binding", bound_context.json()["model_profile_source"])
            self.assertNotIn("stage-profile-secret", json.dumps(bound_context.json()))

            self.assertEqual(200, beta_context.status_code)
            self.assertEqual("default", beta_context.json()["role_name"])
            self.assertEqual("a", beta_context.json()["model_profile_id"])
            self.assertEqual("active", beta_context.json()["model_profile_source"])

    def test_session_centered_admin_projection_apis_split_runtime_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            raw_channel_config = {
                "console": {"enabled": False, "allow_from": []},
                "telegram": {
                    "enabled": True,
                    "allow_from": ["12345"],
                    "mirror_to_stage": True,
                    "stage_session_name": "Telegram Live",
                    "bot_token": "telegram-projection-secret",
                    "proxy": "",
                    "reply_to_message": False,
                },
                "discord": {
                    "enabled": False,
                    "allow_from": ["discord-user"],
                    "mirror_to_stage": True,
                    "stage_session_name": "Discord Live",
                    "bot_token": "discord-projection-secret",
                    "webhook_url": "https://discord.com/api/webhooks/1/token",
                    "webhook_secret": "discord-webhook-projection-secret",
                    "application_id": "discord-app-id",
                    "guild_id": "discord-guild-id",
                },
                "qq": {
                    "enabled": False,
                    "allow_from": ["qq-user"],
                    "mirror_to_stage": False,
                    "app_id": "qq-app-id",
                    "client_secret": "qq-projection-secret",
                },
            }

            with TestClient(app) as client:
                web_config = client.get("/api/web/config")
                live2d_key = web_config.json()["live2d"]["models"][0]["selection_key"]
                updated_profile = update_split_model_profile(
                    client,
                    "b",
                    label="Session Runtime B",
                    chat={
                        "provider": "private-litellm",
                        "model": "session-chat-model",
                        "base_url": "http://session-llm.test/v1",
                        "temperature": 0.3,
                        "max_tokens": 1234,
                        "api_key": "session-chat-secret",
                    },
                    tts={
                        "provider": "openai-compatible",
                        "model": "session-tts-model",
                        "base_url": "http://session-tts.test/v1",
                        "voice": "session-voice",
                        "api_key": "session-tts-secret",
                    },
                    asr={
                        "provider": "openai-transcriptions",
                        "model": "session-stt-model",
                        "base_url": "http://session-stt.test/v1",
                        "language": "zh-TW",
                        "api_key": "session-stt-secret",
                    },
                    live2d={
                        "selection_key": live2d_key,
                    },
                )
                client.post(
                    "/api/roles",
                    json={
                        "name": "Session Host",
                        "prompt": "# Session Host\n\nUse session settings.",
                    },
                )
                set_character_model_binding(client, "session-host", "b")
                switched = client.put(
                    "/api/sessions/default/role",
                    json={"role_name": "session-host"},
                )
                route_mode = client.put(
                    "/api/sessions/default/route-mode",
                    json={"route_mode": "chat_only"},
                )
                client.put("/api/channels/config", json=raw_channel_config)

                llm_models = client.get("/api/llm-models")
                voice_models = client.get("/api/voice-models")
                live2d_models = client.get("/api/live2d-models")
                integrations = client.get("/api/channel-integrations")
                context = client.get("/api/sessions/default/runtime-context")

            self.assertEqual(200, updated_profile.status_code)
            self.assertEqual(200, switched.status_code)
            self.assertEqual(200, route_mode.status_code)

            self.assertEqual(200, llm_models.status_code)
            self.assertEqual("a", llm_models.json()["active_model_id"])
            llm_model = next(
                item for item in llm_models.json()["models"] if item["id"] == "b"
            )
            self.assertEqual("Session Runtime B", llm_model["name"])
            self.assertEqual("private-litellm", llm_model["provider"])
            self.assertEqual("session-chat-model", llm_model["model"])
            self.assertEqual("http://session-llm.test/v1", llm_model["base_url"])
            self.assertEqual(0.3, llm_model["temperature"])
            self.assertEqual(1234, llm_model["max_tokens"])
            self.assertTrue(llm_model["api_key_configured"])
            self.assertEqual("profile", llm_model["api_key_source"])
            self.assertNotIn("tts", llm_model)
            self.assertNotIn("asr", llm_model)

            self.assertEqual(200, voice_models.status_code)
            self.assertEqual("a", voice_models.json()["active_voice_profile_id"])
            voice_profile = next(
                item for item in voice_models.json()["profiles"] if item["id"] == "b"
            )
            self.assertEqual("Session Runtime B", voice_profile["name"])
            self.assertEqual("session-voice", voice_profile["tts"]["voice"])
            self.assertEqual("session-stt-model", voice_profile["stt"]["model"])
            self.assertEqual("zh-TW", voice_profile["stt"]["language"])
            self.assertTrue(voice_profile["tts"]["api_key_configured"])
            self.assertTrue(voice_profile["stt"]["api_key_configured"])

            self.assertEqual(200, live2d_models.status_code)
            self.assertEqual("a", live2d_models.json()["active_live2d_model_id"])
            live2d_profile = next(
                item for item in live2d_models.json()["models"] if item["id"] == "b"
            )
            self.assertEqual("Session Runtime B", live2d_profile["name"])
            self.assertEqual(live2d_key, live2d_profile["selection_key"])
            self.assertTrue(live2d_profile["available"])

            self.assertEqual(200, integrations.status_code)
            telegram = next(
                item for item in integrations.json()["integrations"] if item["id"] == "telegram"
            )
            self.assertEqual("telegram", telegram["type"])
            self.assertTrue(telegram["enabled"])
            self.assertTrue(telegram["configured"])
            self.assertEqual("telegram-live", telegram["stage_session_name"])
            self.assertTrue(telegram["config"]["bot_token_configured"])
            self.assertEqual("", telegram["config"]["bot_token"])
            integration_text = json.dumps(integrations.json())
            self.assertNotIn("telegram-projection-secret", integration_text)
            self.assertNotIn("discord-projection-secret", integration_text)
            self.assertNotIn("discord-webhook-projection-secret", integration_text)
            self.assertNotIn("qq-projection-secret", integration_text)

            self.assertEqual(200, context.status_code)
            self.assertEqual("default", context.json()["session_name"])
            self.assertEqual("session-host", context.json()["role_name"])
            self.assertEqual("chat_only", context.json()["route_mode"])
            self.assertEqual("session-host", context.json()["character"]["name"])
            self.assertEqual("b", context.json()["character"]["effective_model_profile_id"])
            self.assertEqual("session-chat-model", context.json()["llm_model"]["model"])
            self.assertEqual("session-voice", context.json()["voice_profile"]["tts"]["voice"])
            self.assertEqual(live2d_key, context.json()["live2d_model"]["selection_key"])
            self.assertTrue(context.json()["live2d_model"]["model_url"].endswith(".model3.json"))
            self.assertIsNone(context.json()["channel"])
            context_text = json.dumps(context.json())
            self.assertNotIn("session-chat-secret", context_text)
            self.assertNotIn("session-tts-secret", context_text)
            self.assertNotIn("session-stt-secret", context_text)

    def test_console_runtime_overrides_update_stage_context_without_persisting_admin_profiles(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                web_config = client.get("/api/web/config")
                live2d_key = web_config.json()["live2d"]["models"][0]["selection_key"]
                profile = update_split_model_profile(
                    client,
                    "b",
                    label="Console Preview B",
                    chat={
                        "provider": "litellm",
                        "model": "admin-profile-chat",
                        "base_url": "http://admin-profile.test/v1",
                        "api_key": "admin-profile-secret",
                    },
                    tts={
                        "provider": "openai-compatible",
                        "model": "admin-profile-tts",
                        "voice": "admin-profile-voice",
                    },
                    asr={
                        "provider": "openai-transcriptions",
                        "model": "admin-profile-asr",
                    },
                    live2d={
                        "selection_key": live2d_key,
                    },
                )
                applied = client.put(
                    "/api/sessions/default/runtime-overrides",
                    json={
                        "model_profile_id": "b",
                        "llm_model_id": "b",
                        "voice_profile_id": "b",
                        "live2d_model_id": "b",
                        "tts": {
                            "provider": "edge",
                            "voice": "zh-TW-HsiaoChenNeural",
                        },
                        "asr": {
                            "provider": "fake-asr",
                        },
                        "live2d": {
                            "selection_key": live2d_key,
                        },
                        "stage": {
                            "background": {
                                "key": "unit-background",
                                "label": "Unit Background",
                                "url": "/api/web/stage/backgrounds/unit-background.png",
                                "kind": "uploaded",
                                "transform": {
                                    "positionX": 32,
                                    "positionY": 64,
                                    "scale": 125,
                                },
                            },
                        },
                    },
                )
                context = client.get("/api/sessions/default/runtime-context")
                stored_profile = client.get("/api/model-profiles/b")
                unknown = client.put(
                    "/api/sessions/default/runtime-overrides",
                    json={"model_profile_id": "missing-profile"},
                )

            self.assertEqual(200, profile.status_code)
            self.assertEqual(200, applied.status_code)
            self.assertEqual("admin-profile-chat", applied.json()["llm_model"]["model"])
            self.assertEqual("edge", applied.json()["voice_profile"]["tts"]["provider"])
            self.assertEqual(
                "zh-TW-HsiaoChenNeural",
                applied.json()["voice_profile"]["tts"]["voice"],
            )
            self.assertEqual("fake-asr", applied.json()["voice_profile"]["stt"]["provider"])
            self.assertEqual(live2d_key, applied.json()["live2d_model"]["selection_key"])
            self.assertEqual(
                "unit-background",
                applied.json()["stage"]["background"]["key"],
            )
            self.assertEqual(
                125,
                applied.json()["stage"]["background"]["transform"]["scale"],
            )

            self.assertEqual(200, context.status_code)
            self.assertEqual(
                "zh-TW-HsiaoChenNeural",
                context.json()["voice_profile"]["tts"]["voice"],
            )
            self.assertEqual(
                "/api/web/stage/backgrounds/unit-background.png",
                context.json()["stage"]["background"]["url"],
            )

            self.assertEqual(200, stored_profile.status_code)
            self.assertEqual("admin-profile-voice", stored_profile.json()["tts"]["voice"])
            self.assertEqual("openai-compatible", stored_profile.json()["tts"]["provider"])
            self.assertEqual("openai-transcriptions", stored_profile.json()["asr"]["provider"])
            self.assertEqual("admin-profile-chat", stored_profile.json()["chat"]["model"])
            stored_profile_text = json.dumps(stored_profile.json())
            self.assertNotIn("zh-TW-HsiaoChenNeural", stored_profile_text)
            self.assertNotIn("fake-asr", stored_profile_text)
            self.assertNotIn("unit-background", stored_profile_text)
            self.assertNotIn("admin-profile-secret", json.dumps(context.json()))

            self.assertEqual(404, unknown.status_code)
            self.assertIn("Unknown model profile", unknown.json()["detail"])

    def test_llm_model_smoke_uses_openai_compatible_profile_without_returning_secret(
        self,
    ) -> None:
        async def fake_generate(self, messages, **kwargs):
            del self, messages, kwargs
            return LLMResponse(
                message=LLMMessage(role="assistant", content="pong"),
                model="local-litellm-alias",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with patch(
                "echobot.app.routers.model_profiles.OpenAICompatibleProvider.generate",
                fake_generate,
            ):
                with TestClient(app) as client:
                    update_split_model_profile(
                        client,
                        "b",
                        label="Local LiteLLM",
                        chat={
                            "provider": "litellm",
                            "model": "local/echo",
                            "base_url": "http://127.0.0.1:4000/v1",
                            "api_key": "local-litellm-secret",
                        },
                    )
                    smoke = client.post("/api/llm-models/b/smoke")

            self.assertEqual(200, smoke.status_code)
            self.assertTrue(smoke.json()["ok"])
            self.assertEqual("ready", smoke.json()["status"])
            self.assertEqual("litellm", smoke.json()["provider"])
            self.assertEqual("local-litellm-alias", smoke.json()["model"])
            smoke_text = json.dumps(smoke.json())
            self.assertNotIn("local-litellm-secret", smoke_text)

    def test_runtime_model_repositories_map_domain_updates_to_compatibility_store(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_root = Path(temp_dir) / ".echobot"
            model_profiles = ModelProfileService(storage_root)
            llm_repository = LLMModelRepository(model_profiles)
            voice_repository = VoiceModelRepository(model_profiles)
            live2d_repository = Live2DModelRepository(model_profiles)

            llm_profile = llm_repository.create(name="Repo LLM")
            llm_profile = llm_repository.update(
                llm_profile["profile_id"],
                {
                    "provider": "litellm",
                    "model": "repo-chat",
                    "base_url": "http://repo-chat.test/v1",
                    "api_key": "repo-chat-secret",
                },
            )
            llm_repository.activate(llm_profile["profile_id"])

            voice_profile = voice_repository.create(name="Repo Voice")
            voice_profile = voice_repository.update(
                voice_profile["profile_id"],
                {
                    "tts": {
                        "provider": "openai-compatible",
                        "model": "repo-tts",
                        "voice": "repo-voice",
                        "api_key": "repo-tts-secret",
                    },
                    "stt": {
                        "provider": "openai-transcriptions",
                        "model": "repo-stt",
                        "language": "zh-TW",
                        "api_key": "repo-stt-secret",
                    },
                },
            )
            voice_repository.activate(voice_profile["profile_id"])

            live2d_profile = live2d_repository.create(name="Repo Live2D")
            live2d_profile = live2d_repository.update(
                live2d_profile["profile_id"],
                {"selection_key": "repo-live2d"},
            )
            payload = llm_repository.list_payload()
            voice_payload = voice_repository.list_payload()
            live2d_payload = live2d_repository.list_payload()
            runtime_llm = llm_repository.get_runtime_profile(llm_profile["profile_id"])
            runtime_voice = voice_repository.active_runtime_profile()
            stored_text = (storage_root / "model_profiles.json").read_text(
                encoding="utf-8",
            )
            llm_store_text = (storage_root / "llm_models.json").read_text(
                encoding="utf-8",
            )
            voice_store_text = (storage_root / "voice_profiles.json").read_text(
                encoding="utf-8",
            )
            live2d_store_text = (storage_root / "live2d_models.json").read_text(
                encoding="utf-8",
            )

            self.assertEqual("repo-chat", llm_profile["chat"]["model"])
            self.assertEqual("litellm", llm_profile["chat"]["provider"])
            self.assertTrue(llm_profile["chat"]["api_key_configured"])
            self.assertNotIn("api_key", llm_profile["chat"])

            self.assertEqual("repo-tts", voice_profile["tts"]["model"])
            self.assertEqual("repo-stt", voice_profile["asr"]["model"])
            self.assertEqual("zh-TW", voice_profile["asr"]["language"])
            self.assertTrue(voice_profile["tts"]["api_key_configured"])
            self.assertTrue(voice_profile["asr"]["api_key_configured"])

            self.assertEqual("repo-live2d", live2d_profile["live2d"]["selection_key"])
            self.assertEqual(llm_profile["profile_id"], payload["active_profile_id"])
            self.assertTrue(
                any(
                    item["profile_id"] == voice_profile["profile_id"]
                    for item in voice_payload["profiles"]
                ),
            )
            self.assertTrue(
                any(
                    item["profile_id"] == live2d_profile["profile_id"]
                    for item in live2d_payload["profiles"]
                ),
            )
            self.assertEqual("repo-chat-secret", runtime_llm["chat"]["api_key"])
            self.assertEqual("repo-tts-secret", runtime_voice["tts"]["api_key"])
            self.assertEqual("repo-stt-secret", runtime_voice["asr"]["api_key"])
            self.assertNotIn("repo-chat-secret", stored_text)
            self.assertNotIn("repo-tts-secret", stored_text)
            self.assertNotIn("repo-stt-secret", stored_text)
            self.assertNotIn("repo-chat-secret", llm_store_text)
            self.assertNotIn("repo-tts-secret", voice_store_text)
            self.assertNotIn("repo-stt-secret", voice_store_text)
            self.assertIn("repo-live2d", live2d_store_text)

    def test_split_runtime_model_domain_endpoints_crud_without_returning_secrets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                live2d_key = client.get("/api/web/config").json()["live2d"]["models"][0]["selection_key"]
                llm = client.post(
                    "/api/llm-models",
                    json={"name": "Domain LLM", "source_model_id": "a"},
                )
                llm_update = client.patch(
                    f"/api/llm-models/{llm.json()['id']}",
                    json={
                        "name": "Domain LLM Updated",
                        "provider": "litellm",
                        "model": "domain-chat",
                        "base_url": "http://domain-chat.test/v1",
                        "api_key": "domain-chat-secret",
                    },
                )
                llm_activate = client.post(f"/api/llm-models/{llm.json()['id']}/activate")
                voice = client.post(
                    "/api/voice-models",
                    json={"name": "Domain Voice", "source_profile_id": "a"},
                )
                voice_update = client.patch(
                    f"/api/voice-models/{voice.json()['id']}",
                    json={
                        "name": "Domain Voice Updated",
                        "tts": {
                            "provider": "openai-compatible",
                            "model": "domain-tts",
                            "voice": "domain-voice",
                            "api_key": "domain-tts-secret",
                        },
                        "stt": {
                            "provider": "openai-transcriptions",
                            "model": "domain-stt",
                            "language": "zh-TW",
                            "api_key": "domain-stt-secret",
                        },
                    },
                )
                voice_active = client.post(
                    "/api/voice-models",
                    json={"name": "Domain Voice Active", "source_profile_id": "a"},
                )
                live2d = client.post(
                    "/api/live2d-models",
                    json={"name": "Domain Live2D", "source_model_id": "a"},
                )
                live2d_update = client.patch(
                    f"/api/live2d-models/{live2d.json()['id']}",
                    json={
                        "name": "Domain Live2D Updated",
                        "selection_key": live2d_key,
                    },
                )
                llm_models = client.get("/api/llm-models")
                voice_models = client.get("/api/voice-models")
                live2d_models = client.get("/api/live2d-models")
                model_profiles = client.get("/api/model-profiles")
                voice_activate = client.post(
                    f"/api/voice-models/{voice_active.json()['id']}/activate",
                )
                live2d_activate = client.post(f"/api/live2d-models/{live2d.json()['id']}/activate")
                deleted_voice = client.delete(f"/api/voice-models/{voice.json()['id']}")
                llm_after_voice_delete = client.get("/api/llm-models")
                live2d_after_voice_delete = client.get("/api/live2d-models")

            self.assertEqual(200, llm.status_code)
            self.assertEqual("domain-llm", llm.json()["id"])
            self.assertEqual(200, llm_update.status_code)
            self.assertEqual("Domain LLM Updated", llm_update.json()["name"])
            self.assertEqual("litellm", llm_update.json()["provider"])
            self.assertEqual("domain-chat", llm_update.json()["model"])
            self.assertTrue(llm_update.json()["api_key_configured"])
            self.assertNotIn("tts", llm_update.json())
            self.assertNotIn("asr", llm_update.json())
            self.assertNotIn("domain-chat-secret", json.dumps(llm_update.json()))

            self.assertEqual(200, llm_activate.status_code)
            self.assertEqual("domain-llm", llm_activate.json()["active_model_id"])
            self.assertEqual("domain-llm", model_profiles.json()["active_profile_id"])

            self.assertEqual(200, voice_update.status_code)
            self.assertEqual("Domain Voice Updated", voice_update.json()["name"])
            self.assertEqual("domain-voice", voice_update.json()["tts"]["voice"])
            self.assertEqual("domain-stt", voice_update.json()["stt"]["model"])
            voice_text = json.dumps(voice_update.json())
            self.assertNotIn("domain-tts-secret", voice_text)
            self.assertNotIn("domain-stt-secret", voice_text)

            self.assertEqual(200, live2d_update.status_code)
            self.assertEqual("Domain Live2D Updated", live2d_update.json()["name"])
            self.assertEqual(live2d_key, live2d_update.json()["selection_key"])
            self.assertTrue(live2d_update.json()["available"])

            self.assertEqual(200, llm_models.status_code)
            self.assertTrue(
                any(item["id"] == "domain-llm" for item in llm_models.json()["models"]),
            )
            self.assertEqual(200, voice_models.status_code)
            self.assertTrue(
                any(item["id"] == "domain-voice" for item in voice_models.json()["profiles"]),
            )
            self.assertEqual(200, live2d_models.status_code)
            self.assertTrue(
                any(item["id"] == "domain-live2d" for item in live2d_models.json()["models"]),
            )
            self.assertEqual(200, deleted_voice.status_code)
            self.assertFalse(
                any(item["id"] == "domain-voice" for item in deleted_voice.json()["profiles"]),
            )
            self.assertEqual(200, voice_activate.status_code)
            self.assertEqual("domain-voice-active", voice_activate.json()["active_voice_profile_id"])
            self.assertEqual(200, live2d_activate.status_code)
            self.assertEqual("domain-live2d", live2d_activate.json()["active_live2d_model_id"])
            self.assertTrue(
                any(item["id"] == "domain-llm" for item in llm_after_voice_delete.json()["models"]),
            )
            self.assertTrue(
                any(item["id"] == "domain-live2d" for item in live2d_after_voice_delete.json()["models"]),
            )

    def test_character_profiles_bind_llm_voice_and_live2d_for_session_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                web_config = client.get("/api/web/config")
                live2d_key = web_config.json()["live2d"]["models"][0]["selection_key"]
                llm_profile = client.patch(
                    "/api/llm-models/b",
                    json={
                        "name": "Split LLM",
                        "provider": "private-litellm",
                        "model": "split-llm-model",
                        "base_url": "http://split-llm.test/v1",
                        "api_key": "split-llm-secret",
                    },
                )
                voice_profile = client.patch(
                    "/api/voice-models/c",
                    json={
                        "name": "Split Voice",
                        "tts": {
                            "provider": "openai-compatible",
                            "model": "split-tts-model",
                            "base_url": "http://split-tts.test/v1",
                            "voice": "split-voice",
                            "api_key": "split-tts-secret",
                        },
                        "stt": {
                            "provider": "openai-transcriptions",
                            "model": "split-stt-model",
                            "base_url": "http://split-stt.test/v1",
                            "language": "ja",
                            "api_key": "split-stt-secret",
                        },
                    },
                )
                live2d_profile = client.patch(
                    "/api/live2d-models/d",
                    json={
                        "name": "Split Live2D",
                        "selection_key": live2d_key,
                    },
                )
                created = client.post(
                    "/api/character-profiles",
                    json={
                        "name": "Split Host",
                        "prompt": "# Split Host\n\nUse split runtime.",
                        "llm_model_id": "b",
                        "voice_profile_id": "c",
                        "live2d_model_id": "d",
                    },
                )
                switched = client.put(
                    "/api/sessions/default/role",
                    json={"role_name": "split-host"},
                )
                context = client.get("/api/sessions/default/runtime-context")
                runtime = app.state.runtime
                provider_settings = runtime.context.agent.provider.settings

            self.assertEqual(200, llm_profile.status_code)
            self.assertEqual(200, voice_profile.status_code)
            self.assertEqual(200, live2d_profile.status_code)
            self.assertEqual(200, created.status_code)
            self.assertEqual("split-host", created.json()["name"])
            self.assertEqual("b", created.json()["llm_model_id"])
            self.assertEqual("c", created.json()["voice_profile_id"])
            self.assertEqual("d", created.json()["live2d_model_id"])

            self.assertEqual(200, switched.status_code)
            self.assertEqual("split-host", switched.json()["role_name"])

            self.assertEqual(200, context.status_code)
            self.assertEqual("split-host", context.json()["role_name"])
            self.assertEqual("b", context.json()["character"]["llm_model_id"])
            self.assertEqual("c", context.json()["character"]["voice_profile_id"])
            self.assertEqual("d", context.json()["character"]["live2d_model_id"])
            self.assertEqual("split-llm-model", context.json()["llm_model"]["model"])
            self.assertEqual("split-voice", context.json()["voice_profile"]["tts"]["voice"])
            self.assertEqual("split-stt-model", context.json()["voice_profile"]["stt"]["model"])
            self.assertEqual(live2d_key, context.json()["live2d_model"]["selection_key"])
            self.assertTrue(context.json()["live2d_model"]["model_url"].endswith(".model3.json"))
            self.assertEqual("split-llm-model", provider_settings.model)
            self.assertEqual("http://split-llm.test/v1", provider_settings.base_url)
            self.assertEqual("split-llm-secret", provider_settings.api_key)
            context_text = json.dumps(context.json())
            self.assertNotIn("split-llm-secret", context_text)
            self.assertNotIn("split-tts-secret", context_text)
            self.assertNotIn("split-stt-secret", context_text)

    def test_character_profiles_combine_role_prompt_and_model_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            role_file = workspace / ".echobot" / "roles" / "stage-host.md"

            with TestClient(app) as client:
                profile = update_split_model_profile(
                    client,
                    "b",
                    label="Stage Host Voice",
                    chat={
                        "provider": "private-litellm",
                        "model": "stage-host-chat",
                        "base_url": "http://stage-host.test/v1",
                        "api_key": "stage-host-key",
                    },
                    tts={
                        "provider": "openai-compatible",
                        "model": "tts-stage",
                        "base_url": "http://tts.test/v1",
                        "voice": "alloy-stage",
                        "api_key": "tts-secret",
                    },
                    asr={
                        "provider": "openai-transcriptions",
                        "model": "whisper-stage",
                        "base_url": "http://asr.test/v1",
                        "language": "zh",
                    },
                    live2d={
                        "selection_key": "builtin:hiyori_pro_en",
                    },
                )
                created = client.post(
                    "/api/character-profiles",
                    json={
                        "name": "Stage Host",
                        "prompt": "# Stage Host\n\nSpeak clearly.",
                        "model_profile_id": "b",
                        "emotion_maps": [
                            {
                                "emotion": "joy",
                                "expression": "smile.exp3.json",
                                "motion": "wave.motion3.json",
                            },
                        ],
                    },
                )
                listed = client.get("/api/character-profiles")
                detail = client.get("/api/character-profiles/stage-host")
                switched = client.put(
                    "/api/sessions/default/role",
                    json={"role_name": "stage-host"},
                )
                updated = client.patch(
                    "/api/character-profiles/stage-host",
                    json={
                        "prompt": "# Stage Host\n\nSpeak with warm energy.",
                        "model_profile_id": "c",
                        "emotion_maps": [
                            {
                                "emotion": "focused",
                                "expression": "serious.exp3.json",
                                "motion": "nod.motion3.json",
                            },
                        ],
                    },
                )
                mapped_stage_event = client.post(
                    "/api/stage/events",
                    json={
                        "kind": "character_state",
                        "session_name": "default",
                        "emotion": "focused",
                    },
                )
                console_config = client.get("/api/web/config")
                role_bindings = client.get("/api/model-profiles/role-bindings")
                character_settings_after_update = json.loads(
                    (workspace / ".echobot" / "character_profiles.json").read_text(
                        encoding="utf-8",
                    ),
                )
                cleared = client.patch(
                    "/api/character-profiles/stage-host",
                    json={"clear_model_profile_binding": True},
                )
                role_bindings_after_clear = client.get("/api/model-profiles/role-bindings")
                deleted = client.delete("/api/character-profiles/stage-host")
                listed_after_delete = client.get("/api/character-profiles")

            self.assertEqual(200, profile.status_code)
            self.assertEqual(200, created.status_code)
            self.assertEqual("stage-host", created.json()["name"])
            self.assertEqual("b", created.json()["model_profile_id"])
            self.assertEqual("b", created.json()["effective_model_profile_id"])
            self.assertEqual("Stage Host Voice", created.json()["model_profile_label"])
            self.assertEqual("stage-host-chat", created.json()["chat_model"])
            self.assertEqual("alloy-stage", created.json()["tts_voice"])
            self.assertEqual("whisper-stage", created.json()["asr_model"])
            self.assertEqual("builtin:hiyori_pro_en", created.json()["live2d_selection_key"])
            self.assertEqual(
                [
                    {
                        "emotion": "joy",
                        "expression": "smile.exp3.json",
                        "motion": "wave.motion3.json",
                    },
                ],
                created.json()["emotion_maps"],
            )
            self.assertTrue(str(created.json()["source_path"]).endswith("stage-host.md"))

            self.assertEqual(200, listed.status_code)
            listed_names = [item["name"] for item in listed.json()["characters"]]
            self.assertEqual(["default", "stage-host"], listed_names)
            self.assertEqual(5, len(listed.json()["model_profiles"]))

            self.assertEqual(200, detail.status_code)
            self.assertEqual("# Stage Host\n\nSpeak clearly.", detail.json()["prompt"])

            self.assertEqual(200, switched.status_code)
            self.assertEqual("stage-host", switched.json()["role_name"])

            self.assertEqual(200, updated.status_code)
            self.assertEqual("c", updated.json()["model_profile_id"])
            self.assertEqual("# Stage Host\n\nSpeak with warm energy.", updated.json()["prompt"])
            self.assertEqual(
                [
                    {
                        "emotion": "focused",
                        "expression": "serious.exp3.json",
                        "motion": "nod.motion3.json",
                    },
                ],
                updated.json()["emotion_maps"],
            )

            self.assertEqual(200, mapped_stage_event.status_code)
            self.assertEqual("focused", mapped_stage_event.json()["emotion"])
            self.assertEqual("serious.exp3.json", mapped_stage_event.json()["expression"])
            self.assertEqual("nod.motion3.json", mapped_stage_event.json()["motion"])

            self.assertEqual(200, console_config.status_code)
            self.assertEqual("c", console_config.json()["model_profiles"]["active_profile_id"])
            self.assertEqual(200, role_bindings.status_code)
            self.assertEqual("c", role_bindings.json()["stage-host"])
            self.assertEqual(
                "c",
                character_settings_after_update["roles"]["stage-host"]["model_profile_id"],
            )

            self.assertEqual(200, cleared.status_code)
            self.assertEqual("", cleared.json()["model_profile_id"])
            self.assertEqual(200, role_bindings_after_clear.status_code)
            self.assertNotIn("stage-host", role_bindings_after_clear.json())

            self.assertEqual(200, deleted.status_code)
            self.assertTrue(deleted.json()["deleted"])
            self.assertEqual("stage-host", deleted.json()["name"])
            self.assertFalse(role_file.exists())

            self.assertEqual(200, listed_after_delete.status_code)
            self.assertEqual(
                ["default"],
                [item["name"] for item in listed_after_delete.json()["characters"]],
            )

    def test_character_profile_rename_preserves_bindings_and_session_role(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            old_role_file = workspace / ".echobot" / "roles" / "old-host.md"
            new_role_file = workspace / ".echobot" / "roles" / "renamed-host.md"

            with TestClient(app) as client:
                update_split_model_profile(
                    client,
                    "b",
                    label="Rename LLM",
                    chat={
                        "provider": "private-litellm",
                        "model": "rename-chat",
                        "base_url": "http://rename.test/v1",
                    },
                )
                created = client.post(
                    "/api/character-profiles",
                    json={
                        "name": "Old Host",
                        "prompt": "# Old Host\n\nSpeak clearly.",
                        "model_profile_id": "b",
                        "llm_model_id": "b",
                        "default_channel_type": "telegram",
                        "default_channel_integration_id": "telegram",
                        "emotion_maps": [
                            {
                                "emotion": "joy",
                                "expression": "smile.exp3.json",
                                "motion": "wave.motion3.json",
                            },
                        ],
                    },
                )
                session = client.post(
                    "/api/sessions",
                    json={
                        "name": "Rename Session",
                        "role_name": "Old Host",
                    },
                )
                renamed = client.patch(
                    "/api/character-profiles/old-host",
                    json={
                        "name": "Renamed Host",
                        "prompt": "# Renamed Host\n\nKeep the old bindings.",
                    },
                )
                old_detail = client.get("/api/character-profiles/old-host")
                new_detail = client.get("/api/character-profiles/renamed-host")
                session_detail = client.get("/api/sessions/rename-session")
                runtime_context = client.get("/api/sessions/rename-session/runtime-context")

            self.assertEqual(200, created.status_code)
            self.assertEqual(200, session.status_code)
            self.assertTrue(str(created.json()["source_path"]).endswith("old-host.md"))

            self.assertEqual(200, renamed.status_code)
            self.assertEqual("renamed-host", renamed.json()["name"])
            self.assertEqual("# Renamed Host\n\nKeep the old bindings.", renamed.json()["prompt"])
            self.assertEqual("b", renamed.json()["model_profile_id"])
            self.assertEqual("b", renamed.json()["llm_model_id"])
            self.assertEqual("telegram", renamed.json()["default_channel_type"])
            self.assertEqual("telegram", renamed.json()["default_channel_integration_id"])
            self.assertEqual(
                [
                    {
                        "emotion": "joy",
                        "expression": "smile.exp3.json",
                        "motion": "wave.motion3.json",
                    },
                ],
                renamed.json()["emotion_maps"],
            )
            self.assertEqual(404, old_detail.status_code)
            self.assertEqual(200, new_detail.status_code)
            self.assertEqual("renamed-host", new_detail.json()["name"])
            self.assertFalse(old_role_file.exists())
            self.assertTrue(new_role_file.exists())

            self.assertEqual(200, session_detail.status_code)
            self.assertEqual("renamed-host", session_detail.json()["role_name"])
            self.assertEqual("telegram", session_detail.json()["channel_integration_id"])

            self.assertEqual(200, runtime_context.status_code)
            self.assertEqual("renamed-host", runtime_context.json()["role_name"])
            self.assertEqual("rename-chat", runtime_context.json()["llm_model"]["model"])

    def test_character_profile_package_export_import_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                profile = update_split_model_profile(
                    client,
                    "b",
                    label="Package Voice",
                    chat={
                        "provider": "private-litellm",
                        "model": "package-chat",
                        "base_url": "http://package.test/v1",
                        "api_key": "package-secret-key",
                    },
                    tts={
                        "provider": "openai-compatible",
                        "model": "tts-package",
                        "base_url": "http://tts-package.test/v1",
                        "voice": "alloy-package",
                        "api_key": "tts-package-secret",
                    },
                    live2d={
                        "selection_key": "builtin:hiyori_pro_en",
                    },
                )
                created = client.post(
                    "/api/character-profiles",
                    json={
                        "name": "Package Host",
                        "prompt": "# Package Host\n\nSpeak from a package.",
                        "model_profile_id": "b",
                        "default_channel_type": "telegram",
                        "default_channel_integration_id": "telegram",
                        "emotion_maps": [
                            {
                                "emotion": "joy",
                                "expression": "smile.exp3.json",
                                "motion": "wave.motion3.json",
                            },
                        ],
                    },
                )
                exported = client.get("/api/character-profiles/package-host/package")
                package_payload = exported.json()
                package_text = json.dumps(package_payload)
                imported = client.post(
                    "/api/character-profiles/package",
                    json={
                        **package_payload,
                        "import_name": "Imported Host",
                    },
                )
                duplicate = client.post(
                    "/api/character-profiles/package",
                    json={
                        **package_payload,
                        "import_name": "Imported Host",
                    },
                )
                overwritten = client.post(
                    "/api/character-profiles/package",
                    json={
                        **package_payload,
                        "import_name": "Imported Host",
                        "overwrite": True,
                        "character": {
                            **package_payload["character"],
                            "prompt": "# Imported Host\n\nOverwritten.",
                            "emotion_maps": [
                                {
                                    "emotion": "focused",
                                    "expression": "serious.exp3.json",
                                    "motion": "nod.motion3.json",
                                },
                            ],
                        },
                    },
                )
                listed = client.get("/api/character-profiles")
                bad_version = client.post(
                    "/api/character-profiles/package",
                    json={
                        **package_payload,
                        "package_version": 999,
                        "import_name": "Bad Version",
                    },
                )
                malformed = client.post(
                    "/api/character-profiles/package",
                    json={
                        "package_version": 1,
                        "character": "not-object",
                    },
                )
                too_long = client.post(
                    "/api/character-profiles/package",
                    json={
                        **package_payload,
                        "import_name": "Too Long",
                        "character": {
                            **package_payload["character"],
                            "prompt": "x" * 60001,
                        },
                    },
                )

            self.assertEqual(200, profile.status_code)
            self.assertEqual(200, created.status_code)

            self.assertEqual(200, exported.status_code)
            self.assertEqual(1, package_payload["package_version"])
            self.assertEqual("package-host", package_payload["character"]["name"])
            self.assertEqual("# Package Host\n\nSpeak from a package.", package_payload["character"]["prompt"])
            self.assertEqual("b", package_payload["character"]["model_profile_id"])
            self.assertEqual("telegram", package_payload["character"]["default_channel_type"])
            self.assertEqual(
                "telegram",
                package_payload["character"]["default_channel_integration_id"],
            )
            self.assertEqual(
                [
                    {
                        "emotion": "joy",
                        "expression": "smile.exp3.json",
                        "motion": "wave.motion3.json",
                    },
                ],
                package_payload["character"]["emotion_maps"],
            )
            self.assertEqual("b", package_payload["model_profile_snapshot"]["profile_id"])
            self.assertEqual("package-chat", package_payload["model_profile_snapshot"]["chat"]["model"])
            self.assertTrue(package_payload["model_profile_snapshot"]["chat"]["api_key_configured"])
            self.assertNotIn("package-secret-key", package_text)
            self.assertNotIn("tts-package-secret", package_text)
            self.assertNotIn('"api_key":', package_text)

            self.assertEqual(200, imported.status_code)
            self.assertEqual("imported-host", imported.json()["name"])
            self.assertEqual("b", imported.json()["model_profile_id"])
            self.assertEqual("telegram", imported.json()["default_channel_type"])
            self.assertEqual("telegram", imported.json()["default_channel_integration_id"])
            self.assertEqual("joy", imported.json()["emotion_maps"][0]["emotion"])

            self.assertEqual(409, duplicate.status_code)

            self.assertEqual(200, overwritten.status_code)
            self.assertEqual("# Imported Host\n\nOverwritten.", overwritten.json()["prompt"])
            self.assertEqual("focused", overwritten.json()["emotion_maps"][0]["emotion"])

            self.assertEqual(200, listed.status_code)
            self.assertIn("imported-host", [item["name"] for item in listed.json()["characters"]])

            self.assertEqual(400, bad_version.status_code)
            self.assertEqual(400, malformed.status_code)
            self.assertEqual(400, too_long.status_code)

    def test_openwebui_bridge_targets_user_scoped_stage_and_chat(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN": "bridge-secret",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

                auth_headers = {"Authorization": "Bearer bridge-secret"}
                with TestClient(app) as client:
                    missing_target = client.post(
                        "/api/openwebui/chat",
                        headers=auth_headers,
                        json={
                            "session_name": "demo",
                            "prompt": "ping",
                        },
                    )
                    stage_event = client.post(
                        "/api/openwebui/stage/events",
                        headers=auth_headers,
                        json={
                            "target_user_id": "alpha@example.test",
                            "session_name": "demo",
                            "text": "hello from Open WebUI",
                            "emotion": "joy",
                            "expression": "smile.exp3.json",
                            "motion": "wave.motion3.json",
                            "speaker": "Operator",
                        },
                    )
                    chat = client.post(
                        "/api/openwebui/chat",
                        headers=auth_headers,
                        json={
                            "target_user_id": "alpha@example.test",
                            "session_name": "demo",
                            "prompt": "ping",
                        },
                    )
                    alpha_sessions = client.get(
                        "/api/openwebui/sessions?target_user_id=alpha@example.test",
                        headers=auth_headers,
                    )
                    beta_sessions = client.get(
                        "/api/openwebui/sessions?target_user_id=beta@example.test",
                        headers=auth_headers,
                    )
                    force_agent = client.post(
                        "/api/openwebui/chat",
                        headers=auth_headers,
                        json={
                            "target_user_id": "alpha@example.test",
                            "session_name": "demo",
                            "prompt": "run tools",
                            "route_mode": "force_agent",
                        },
                    )

                    runtime = app.state.runtime
                    alpha_history = runtime.stage_event_broker.history(
                        user_storage_key("alpha@example.test"),
                        "demo",
                    )
                    beta_history = runtime.stage_event_broker.history(
                        user_storage_key("beta@example.test"),
                        "demo",
                    )

            self.assertEqual(400, missing_target.status_code)
            self.assertEqual("target_user_id is required", missing_target.json()["detail"])
            self.assertEqual(200, stage_event.status_code)
            self.assertEqual("assistant_final", stage_event.json()["kind"])
            self.assertEqual("openwebui", stage_event.json()["source"])
            self.assertEqual("joy", stage_event.json()["emotion"])
            self.assertEqual("smile.exp3.json", stage_event.json()["expression"])
            self.assertEqual("wave.motion3.json", stage_event.json()["motion"])
            self.assertEqual(
                ["hello from Open WebUI", "pong"],
                [item.text for item in alpha_history],
            )
            self.assertEqual("openwebui", alpha_history[1].source)
            self.assertEqual("chat", alpha_history[1].metadata["openwebui_operation"])
            self.assertEqual([], beta_history)
            self.assertEqual(200, chat.status_code)
            self.assertEqual("demo", chat.json()["session_name"])
            self.assertEqual("pong", chat.json()["response"])
            self.assertEqual(200, alpha_sessions.status_code)
            self.assertIn("demo", [item["name"] for item in alpha_sessions.json()])
            self.assertEqual(200, beta_sessions.status_code)
            self.assertNotIn("demo", [item["name"] for item in beta_sessions.json()])
            self.assertEqual(403, force_agent.status_code)
            self.assertEqual(
                "Open WebUI operator-agent mode is disabled",
                force_agent.json()["detail"],
            )

    def test_openwebui_bridge_default_user_and_allowed_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                    "ECHOBOT_OPENWEBUI_BRIDGE_TOKEN": "bridge-secret",
                    "ECHOBOT_OPENWEBUI_BRIDGE_USER_ID": "alpha@example.test",
                    "ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS": "alpha@example.test",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

                auth_headers = {"Authorization": "Bearer bridge-secret"}
                with TestClient(app) as client:
                    default_user_chat = client.post(
                        "/api/openwebui/chat",
                        headers=auth_headers,
                        json={
                            "session_name": "demo",
                            "prompt": "ping",
                        },
                    )
                    disallowed_stage = client.post(
                        "/api/openwebui/stage/events",
                        headers=auth_headers,
                        json={
                            "target_user_id": "beta@example.test",
                            "session_name": "demo",
                            "text": "blocked",
                        },
                    )

                    runtime = app.state.runtime
                    alpha_history = runtime.stage_event_broker.history(
                        user_storage_key("alpha@example.test"),
                        "demo",
                    )
                    beta_history = runtime.stage_event_broker.history(
                        user_storage_key("beta@example.test"),
                        "demo",
                    )

            self.assertEqual(200, default_user_chat.status_code)
            self.assertEqual("demo", default_user_chat.json()["session_name"])
            self.assertEqual(403, disallowed_stage.status_code)
            self.assertEqual("target_user_id is not allowed", disallowed_stage.json()["detail"])
            self.assertEqual(["pong"], [item.text for item in alpha_history])
            self.assertEqual([], beta_history)

    def test_trusted_user_header_isolates_sessions_jobs_and_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

            alpha_headers = {DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"}
            beta_headers = {DEFAULT_TRUSTED_USER_HEADER: "beta@example.test"}

            with TestClient(app) as client:
                alpha_session = client.post(
                    "/api/sessions",
                    json={"name": "demo"},
                    headers=alpha_headers,
                )
                alpha_reply = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "ping",
                    },
                    headers=alpha_headers,
                )
                alpha_upload = client.post(
                    "/api/attachments/files",
                    files={
                        "file": (
                            "note.txt",
                            make_chat_text_bytes(),
                            "text/plain",
                        )
                    },
                    headers=alpha_headers,
                )
                alpha_job = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                    headers=alpha_headers,
                )
                alpha_jobs = client.get(
                    "/api/chat/jobs?session_name=demo",
                    headers=alpha_headers,
                )
                beta_sessions = client.get("/api/sessions", headers=beta_headers)
                beta_demo = client.get("/api/sessions/demo", headers=beta_headers)
                beta_jobs = client.get(
                    "/api/chat/jobs?session_name=demo",
                    headers=beta_headers,
                )
                beta_download = client.get(
                    alpha_upload.json()["download_url"],
                    headers=beta_headers,
                )

            self.assertEqual(200, alpha_session.status_code)
            self.assertEqual(200, alpha_reply.status_code)
            self.assertEqual("pong", alpha_reply.json()["response"])
            self.assertEqual(200, alpha_upload.status_code)
            self.assertIn(
                f".echobot/users/{user_storage_key('alpha@example.test')}/attachments/",
                alpha_upload.json()["workspace_path"],
            )
            self.assertEqual(200, alpha_job.status_code)
            self.assertTrue(alpha_job.json()["job_id"])
            self.assertEqual(200, alpha_jobs.status_code)
            self.assertEqual(1, len(alpha_jobs.json()["jobs"]))
            self.assertEqual(200, beta_sessions.status_code)
            self.assertNotIn("demo", [item["name"] for item in beta_sessions.json()])
            self.assertEqual(404, beta_demo.status_code)
            self.assertEqual(200, beta_jobs.status_code)
            self.assertEqual([], beta_jobs.json()["jobs"])
            self.assertEqual(404, beta_download.status_code)

    def test_trusted_user_header_applies_to_asr_websocket(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                    tts_service_builder=build_test_tts_service,
                    asr_service_builder=build_test_asr_service,
                )

            with TestClient(app) as client:
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect("/api/web/asr/ws"):
                        pass

                with client.websocket_connect(
                    "/api/web/asr/ws",
                    headers={DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"},
                ) as websocket:
                    ready = websocket.receive_json()

            self.assertEqual("ready", ready["type"])
            self.assertEqual(16000, ready["sample_rate"])

    def test_trusted_user_header_isolates_asr_provider_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                    tts_service_builder=build_test_tts_service,
                    asr_service_builder=build_test_asr_service,
                )

            alpha_headers = {DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"}
            beta_headers = {DEFAULT_TRUSTED_USER_HEADER: "beta@example.test"}

            with TestClient(app) as client:
                alpha_initial = client.get("/api/web/config", headers=alpha_headers)
                beta_initial = client.get("/api/web/config", headers=beta_headers)
                updated = client.patch(
                    "/api/web/asr/provider",
                    json={"provider": "backup-asr"},
                    headers=alpha_headers,
                )
                alpha_config = client.get("/api/web/config", headers=alpha_headers)
                beta_config = client.get("/api/web/config", headers=beta_headers)

            self.assertEqual(200, alpha_initial.status_code)
            self.assertEqual("fake-asr", alpha_initial.json()["asr"]["selected_asr_provider"])
            self.assertEqual(200, beta_initial.status_code)
            self.assertEqual("fake-asr", beta_initial.json()["asr"]["selected_asr_provider"])
            self.assertEqual(200, updated.status_code)
            self.assertEqual("backup-asr", updated.json()["selected_asr_provider"])
            self.assertEqual(200, alpha_config.status_code)
            self.assertEqual("backup-asr", alpha_config.json()["asr"]["selected_asr_provider"])
            self.assertEqual(200, beta_config.status_code)
            self.assertEqual("fake-asr", beta_config.json()["asr"]["selected_asr_provider"])

            alpha_settings_path = (
                workspace
                / ".echobot"
                / "users"
                / user_storage_key("alpha@example.test")
                / "runtime_settings.json"
            )
            beta_settings_path = (
                workspace
                / ".echobot"
                / "users"
                / user_storage_key("beta@example.test")
                / "runtime_settings.json"
            )
            alpha_settings = json.loads(alpha_settings_path.read_text(encoding="utf-8"))
            self.assertEqual("backup-asr", alpha_settings["selected_asr_provider"])
            if beta_settings_path.exists():
                beta_settings = json.loads(beta_settings_path.read_text(encoding="utf-8"))
                self.assertNotIn("selected_asr_provider", beta_settings)

    def test_stage_event_api_validates_and_scopes_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with patch.dict(
                os.environ,
                {
                    "ECHOBOT_TRUSTED_USER_HEADER_ENABLED": "true",
                    "ECHOBOT_TRUSTED_USER_REQUIRED": "true",
                },
                clear=False,
            ):
                app = create_app(
                    runtime_options=RuntimeOptions(
                        workspace=workspace,
                        no_tools=True,
                        no_skills=True,
                        no_memory=True,
                        no_heartbeat=True,
                    ),
                    channel_config_path=workspace / ".echobot" / "channels.json",
                    context_builder=build_test_context,
                )

            alpha_headers = {DEFAULT_TRUSTED_USER_HEADER: "alpha@example.test"}
            beta_headers = {DEFAULT_TRUSTED_USER_HEADER: "beta@example.test"}

            with TestClient(app) as client:
                wrong_content_type = client.post(
                    "/api/stage/events",
                    data="{}",
                    headers={
                        **alpha_headers,
                        "content-type": "text/plain",
                    },
                )
                malformed_json = client.post(
                    "/api/stage/events",
                    content=b"{",
                    headers={
                        **alpha_headers,
                        "content-type": "application/json",
                    },
                )
                too_large_text = client.post(
                    "/api/stage/events",
                    json={
                        "kind": "assistant_final",
                        "session_name": "demo",
                        "text": "x" * 8193,
                    },
                    headers=alpha_headers,
                )
                too_large_metadata = client.post(
                    "/api/stage/events",
                    json={
                        "kind": "assistant_final",
                        "session_name": "demo",
                        "text": "hello",
                        "metadata": {"payload": "x" * 4097},
                    },
                    headers=alpha_headers,
                )
                alpha_event = client.post(
                    "/api/stage/events",
                    json={
                        "kind": "assistant_final",
                        "session_name": "demo",
                        "text": "hello stage",
                        "speaker": "Echo",
                        "source": "messenger",
                        "emotion": "joy",
                        "expression": "smile.exp3.json",
                        "motion": "wave.motion3.json",
                    },
                    headers=alpha_headers,
                )
                beta_event = client.post(
                    "/api/stage/events",
                    json={
                        "kind": "assistant_final",
                        "session_name": "demo",
                        "text": "beta stage",
                        "source": "messenger",
                    },
                    headers=beta_headers,
                )

                runtime = app.state.runtime
                alpha_history = runtime.stage_event_broker.history(
                    user_storage_key("alpha@example.test"),
                    "demo",
                )
                beta_history = runtime.stage_event_broker.history(
                    user_storage_key("beta@example.test"),
                    "demo",
                )
                alpha_other_session = runtime.stage_event_broker.history(
                    user_storage_key("alpha@example.test"),
                    "other",
                )

            self.assertEqual(415, wrong_content_type.status_code)
            self.assertEqual(400, malformed_json.status_code)
            self.assertEqual(400, too_large_text.status_code)
            self.assertEqual(400, too_large_metadata.status_code)
            self.assertEqual(200, alpha_event.status_code)
            self.assertEqual("evt_000001", alpha_event.json()["event_id"])
            self.assertEqual("assistant_final", alpha_event.json()["kind"])
            self.assertEqual("joy", alpha_event.json()["emotion"])
            self.assertEqual("smile.exp3.json", alpha_event.json()["expression"])
            self.assertEqual("wave.motion3.json", alpha_event.json()["motion"])
            self.assertEqual(200, beta_event.status_code)
            self.assertEqual(["hello stage"], [item.text for item in alpha_history])
            self.assertEqual(["beta stage"], [item.text for item in beta_history])
            self.assertEqual([], alpha_other_session)

    def test_stage_event_sse_route_replays_published_event(self) -> None:
        async def read_first_sse_payload(runtime) -> tuple[str, dict[str, str], str]:
            response = await subscribe_stage_events(
                session_name="demo",
                runtime=runtime,
            )
            iterator = response.body_iterator
            try:
                payload = await asyncio.wait_for(anext(iterator), timeout=0.2)
            finally:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
            return response.media_type or "", dict(response.headers), payload

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                published = client.post(
                    "/api/stage/events",
                    json={
                        "kind": "assistant_delta",
                        "session_name": "demo",
                        "text": "po",
                        "speaker": "EchoBot",
                        "source": "messenger",
                    },
                )
                media_type, headers, payload = asyncio.run(
                    read_first_sse_payload(app.state.runtime),
                )

            self.assertEqual(200, published.status_code)
            self.assertEqual("text/event-stream", media_type)
            self.assertIn("x-accel-buffering", headers)
            self.assertIn("event: assistant_delta", payload)
            self.assertIn('"text": "po"', payload)
            self.assertIn('"source": "messenger"', payload)

    def test_session_and_chat_endpoints_share_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                created = client.post("/api/sessions", json={"name": "demo"})
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "ping",
                    },
                )
                current = client.get("/api/sessions/current")
                detail = client.get("/api/sessions/demo")

            self.assertEqual(200, created.status_code)
            self.assertEqual("demo", created.json()["name"])
            self.assertEqual(200, replied.status_code)
            self.assertEqual("demo", replied.json()["session_name"])
            self.assertEqual("pong", replied.json()["response"])
            self.assertEqual("pong", replied.json()["response_content"])
            self.assertFalse(replied.json()["delegated"])
            self.assertTrue(replied.json()["completed"])
            self.assertEqual("default", replied.json()["role_name"])
            self.assertEqual(200, current.status_code)
            self.assertEqual("demo", current.json()["name"])
            self.assertEqual(200, detail.status_code)
            self.assertEqual("default", detail.json()["role_name"])
            self.assertEqual("auto", detail.json()["route_mode"])
            self.assertEqual(2, len(detail.json()["history"]))
            self.assertEqual("user", detail.json()["history"][0]["role"])
            self.assertEqual("assistant", detail.json()["history"][1]["role"])

    def test_session_create_can_bind_character_and_channel_integration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                role = client.post(
                    "/api/roles",
                    json={
                        "name": "Session Host",
                        "prompt": "# Session Host\n\nOperate this session.",
                    },
                )
                character = client.post(
                    "/api/character-profiles",
                    json={
                        "name": "Telegram Host",
                        "prompt": "# Telegram Host\n\nUse Telegram by default.",
                        "default_channel_type": "telegram",
                        "default_channel_integration_id": "telegram",
                    },
                )
                client.put(
                    "/api/channels/config",
                    json={
                        "telegram": {
                            "enabled": True,
                            "allow_from": ["12345"],
                            "mirror_to_stage": False,
                            "stage_session_name": "other-stage",
                            "bot_token": "session-channel-secret",
                        },
                    },
                )
                default_bound = client.post(
                    "/api/sessions",
                    json={
                        "name": "Character Default Session",
                        "role_name": "Telegram Host",
                        "route_mode": "chat_only",
                    },
                )
                listed = client.get("/api/sessions")
                created = client.post(
                    "/api/sessions",
                    json={
                        "name": "Live Session",
                        "role_name": "Session Host",
                        "route_mode": "chat_only",
                        "channel_type": "telegram",
                        "channel_integration_id": "telegram",
                    },
                )
                detail = client.get("/api/sessions/live-session")
                context = client.get("/api/sessions/live-session/runtime-context")

            self.assertEqual(200, role.status_code)
            self.assertEqual(200, character.status_code)
            self.assertEqual(200, default_bound.status_code)
            self.assertEqual("character-default-session", default_bound.json()["name"])
            self.assertEqual("telegram-host", default_bound.json()["role_name"])
            self.assertEqual("telegram", default_bound.json()["channel_type"])
            self.assertEqual("telegram", default_bound.json()["channel_integration_id"])
            default_summary = next(
                item for item in listed.json() if item["name"] == "character-default-session"
            )
            self.assertEqual("telegram-host", default_summary["role_name"])
            self.assertEqual("telegram", default_summary["channel_integration_id"])
            self.assertEqual(200, created.status_code)
            self.assertEqual("live-session", created.json()["name"])
            self.assertEqual("session-host", created.json()["role_name"])
            self.assertEqual("chat_only", created.json()["route_mode"])
            self.assertEqual("telegram", created.json()["channel_type"])
            self.assertEqual("telegram", created.json()["channel_integration_id"])
            self.assertEqual(200, detail.status_code)
            self.assertEqual("session-host", detail.json()["role_name"])
            self.assertEqual("telegram", detail.json()["channel_integration_id"])
            self.assertEqual(200, context.status_code)
            self.assertEqual("session-host", context.json()["role_name"])
            self.assertEqual("telegram", context.json()["channel"]["id"])
            context_text = json.dumps(context.json())
            self.assertNotIn("session-channel-secret", context_text)

    def test_session_channel_binding_can_be_updated_after_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                client.put(
                    "/api/channels/config",
                    json={
                        "telegram": {
                            "enabled": True,
                            "allow_from": ["12345"],
                            "mirror_to_stage": True,
                            "stage_session_name": "legacy-stage",
                            "bot_token": "session-channel-secret",
                        },
                        "discord": {
                            "enabled": True,
                            "allow_from": ["discord-user"],
                            "mirror_to_stage": True,
                            "stage_session_name": "discord-stage",
                            "webhook_url": "https://discord.example/webhook",
                            "webhook_secret": "discord-secret",
                        },
                    },
                )
                client.post("/api/sessions", json={"name": "ops-room"})
                updated = client.put(
                    "/api/sessions/ops-room/channel-binding",
                    json={
                        "channel_type": "discord",
                        "channel_integration_id": "discord",
                    },
                )
                context = client.get("/api/sessions/ops-room/runtime-context")
                cleared = client.put(
                    "/api/sessions/ops-room/channel-binding",
                    json={
                        "channel_type": "",
                        "channel_integration_id": "",
                    },
                )

            self.assertEqual(200, updated.status_code)
            self.assertEqual("discord", updated.json()["channel_type"])
            self.assertEqual("discord", updated.json()["channel_integration_id"])
            self.assertEqual(200, context.status_code)
            self.assertEqual("discord", context.json()["channel"]["id"])
            self.assertEqual(200, cleared.status_code)
            self.assertEqual("", cleared.json()["channel_type"])
            self.assertEqual("", cleared.json()["channel_integration_id"])

    def test_chat_endpoint_accepts_image_only_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                uploaded = client.post(
                    "/api/attachments/images",
                    files={
                        "file": (
                            "cat.png",
                            make_chat_png_bytes(),
                            "image/png",
                        )
                    },
                )
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "vision",
                        "prompt": "",
                        "images": [
                            {
                                "attachment_id": uploaded.json()["attachment_id"],
                            }
                        ],
                    },
                )
                detail = client.get("/api/sessions/vision")

            self.assertEqual(200, uploaded.status_code)
            self.assertEqual(200, replied.status_code)
            self.assertEqual("pong", replied.json()["response"])
            self.assertEqual(200, detail.status_code)
            self.assertIsInstance(detail.json()["history"][0]["content"], list)
            self.assertTrue(
                detail.json()["history"][0]["content"][0]["image_url"]["url"].startswith("attachment://")
            )
            self.assertTrue(
                detail.json()["history"][0]["content"][0]["image_url"]["preview_url"].startswith(
                    "/api/attachments/",
                )
            )

    def test_chat_endpoint_ignores_images_when_vision_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                runtime = client.app.state.runtime
                runtime.context.supports_image_input = False
                uploaded = client.post(
                    "/api/attachments/images",
                    files={
                        "file": (
                            "cat.png",
                            make_chat_png_bytes(),
                            "image/png",
                        )
                    },
                )
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "vision-off",
                        "prompt": "",
                        "images": [
                            {
                                "attachment_id": uploaded.json()["attachment_id"],
                            }
                        ],
                    },
                )
                detail = client.get("/api/sessions/vision-off")

            self.assertEqual(200, uploaded.status_code)
            self.assertEqual(200, replied.status_code)
            self.assertEqual("pong", replied.json()["response"])
            self.assertEqual(200, detail.status_code)
            self.assertEqual("", detail.json()["history"][0]["content"])

    def test_chat_endpoint_returns_structured_response_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                runtime = client.app.state.runtime
                session = runtime.context.session_store.load_or_create_session("demo")

                async def fake_run_prompt(*args, **kwargs):
                    del args, kwargs
                    return SimpleNamespace(
                        session=session,
                        response_text="Attached the report.",
                        response_content=[
                            {
                                "type": "text",
                                "text": "Attached the report.",
                            },
                            {
                                "type": "file_attachment",
                                "file_attachment": {
                                    "attachment_id": "file_demo",
                                    "name": "report.txt",
                                    "download_url": "/api/attachments/file_demo/content",
                                    "workspace_path": "report.txt",
                                    "content_type": "text/plain",
                                    "size_bytes": 5,
                                },
                            },
                        ],
                        delegated=False,
                        completed=True,
                        job_id=None,
                        status="completed",
                        role_name="default",
                        steps=1,
                        compressed_summary="",
                    )

                runtime.chat_service.run_prompt = fake_run_prompt
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "send the report",
                    },
                )

            self.assertEqual(200, replied.status_code)
            payload = replied.json()
            self.assertEqual("Attached the report.", payload["response"])
            self.assertIsInstance(payload["response_content"], list)
            self.assertEqual("text", payload["response_content"][0]["type"])
            self.assertEqual("file_attachment", payload["response_content"][1]["type"])

    def test_chat_endpoint_accepts_file_only_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                uploaded = client.post(
                    "/api/attachments/files",
                    files={
                        "file": (
                            "notes.txt",
                            make_chat_text_bytes(),
                            "text/plain",
                        )
                    },
                )
                upload_payload = uploaded.json()
                downloaded = client.get(upload_payload["download_url"])
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "files",
                        "prompt": "帮我看看这个文件是做什么的",
                        "files": [
                            {
                                "attachment_id": upload_payload["attachment_id"],
                            }
                        ],
                    },
                )
                detail = client.get("/api/sessions/files")

            self.assertEqual(200, uploaded.status_code)
            self.assertTrue(upload_payload["attachment_id"].startswith("file_"))
            self.assertEqual("text/plain", upload_payload["content_type"])
            self.assertTrue(upload_payload["download_url"].startswith("/api/attachments/"))
            self.assertTrue(upload_payload["workspace_path"].startswith(".echobot/attachments/files/file_"))
            self.assertTrue(upload_payload["workspace_path"].endswith(".txt"))

            self.assertEqual(200, downloaded.status_code)
            self.assertTrue(downloaded.headers["content-type"].startswith("text/plain"))
            self.assertEqual(make_chat_text_bytes(), downloaded.content)

            self.assertEqual(200, replied.status_code)
            self.assertEqual("pong", replied.json()["response"])
            self.assertEqual(200, detail.status_code)
            user_content = detail.json()["history"][0]["content"]
            self.assertIsInstance(user_content, list)
            self.assertEqual("text", user_content[0]["type"])
            self.assertEqual("帮我看看这个文件是做什么的", user_content[0]["text"])
            self.assertEqual("file_attachment", user_content[1]["type"])
            self.assertEqual("notes.txt", user_content[1]["file_attachment"]["name"])
            self.assertEqual(
                upload_payload["attachment_id"],
                user_content[1]["file_attachment"]["attachment_id"],
            )
            self.assertEqual(
                upload_payload["download_url"],
                user_content[1]["file_attachment"]["download_url"],
            )
            self.assertEqual(
                upload_payload["size_bytes"],
                user_content[1]["file_attachment"]["size_bytes"],
            )

    def test_chat_endpoint_rejects_wrong_attachment_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                uploaded = client.post(
                    "/api/attachments/files",
                    files={
                        "file": (
                            "notes.txt",
                            make_chat_text_bytes(),
                            "text/plain",
                        )
                    },
                )
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "wrong-kind",
                        "prompt": "",
                        "images": [
                            {
                                "attachment_id": uploaded.json()["attachment_id"],
                            }
                        ],
                    },
                )

            self.assertEqual(200, uploaded.status_code)
            self.assertEqual(400, replied.status_code)
            self.assertIn("not an image", replied.json()["detail"])

    def test_chat_endpoint_keeps_chat_only_route_for_file_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                runtime = client.app.state.runtime
                runtime.context.tool_registry_factory = (
                    lambda *_args: SimpleNamespace(names=lambda: ["read_text_file"])
                )
                switched = client.put(
                    "/api/sessions/default/route-mode",
                    json={"route_mode": "chat_only"},
                )
                uploaded = client.post(
                    "/api/attachments/files",
                    files={
                        "file": (
                            "notes.txt",
                            make_chat_text_bytes(),
                            "text/plain",
                        )
                    },
                )
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "default",
                        "prompt": "Please set a cron reminder",
                        "files": [
                            {
                                "attachment_id": uploaded.json()["attachment_id"],
                            }
                        ],
                    },
                )
                detail = client.get("/api/sessions/default")

            self.assertEqual(200, switched.status_code)
            self.assertEqual(200, uploaded.status_code)
            self.assertEqual(200, replied.status_code)
            self.assertFalse(replied.json()["delegated"])
            self.assertEqual("pong", replied.json()["response"])
            self.assertEqual(200, detail.status_code)
            self.assertEqual("chat_only", detail.json()["route_mode"])

    def test_route_mode_endpoint_and_chat_overrides_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                switched = client.put(
                    "/api/sessions/default/route-mode",
                    json={"route_mode": "chat_only"},
                )
                direct_reply = client.post(
                    "/api/chat",
                    json={
                        "session_name": "default",
                        "prompt": "Please set a cron reminder",
                    },
                )
                forced_reply = client.post(
                    "/api/chat",
                    json={
                        "session_name": "default",
                        "prompt": "ping",
                        "route_mode": "force_agent",
                    },
                )
                detail = client.get("/api/sessions/default")

            self.assertEqual(200, switched.status_code)
            self.assertEqual("chat_only", switched.json()["route_mode"])

            self.assertEqual(200, direct_reply.status_code)
            self.assertFalse(direct_reply.json()["delegated"])
            self.assertTrue(direct_reply.json()["completed"])
            self.assertEqual("pong", direct_reply.json()["response"])

            self.assertEqual(200, forced_reply.status_code)
            self.assertTrue(forced_reply.json()["delegated"])
            self.assertFalse(forced_reply.json()["completed"])
            self.assertEqual("working", forced_reply.json()["response"])
            self.assertTrue(forced_reply.json()["job_id"])

            self.assertEqual(200, detail.status_code)
            self.assertEqual("chat_only", detail.json()["route_mode"])

    def test_role_endpoints_support_crud_and_session_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            role_file = workspace / ".echobot" / "roles" / "helper-cat.md"

            with TestClient(app) as client:
                created = client.post(
                    "/api/roles",
                    json={
                        "name": "Helper Cat",
                        "prompt": "# Helper Cat\n\nStay concise.",
                    },
                )
                listed = client.get("/api/roles")
                detail = client.get("/api/roles/helper-cat")
                switched = client.put(
                    "/api/sessions/default/role",
                    json={"role_name": "helper-cat"},
                )
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "default",
                        "prompt": "ping",
                    },
                )
                deleted = client.delete("/api/roles/helper-cat")
                current = client.get("/api/sessions/current")
                listed_after_delete = client.get("/api/roles")

            self.assertEqual(200, created.status_code)
            self.assertEqual("helper-cat", created.json()["name"])
            self.assertTrue(created.json()["editable"])
            self.assertTrue(str(created.json()["source_path"]).endswith("helper-cat.md"))

            self.assertEqual(200, listed.status_code)
            self.assertEqual(["default", "helper-cat"], [item["name"] for item in listed.json()])

            self.assertEqual(200, detail.status_code)
            self.assertEqual("# Helper Cat\n\nStay concise.", detail.json()["prompt"])

            self.assertEqual(200, switched.status_code)
            self.assertEqual("helper-cat", switched.json()["role_name"])

            self.assertEqual(200, replied.status_code)
            self.assertEqual("helper-cat", replied.json()["role_name"])

            self.assertEqual(200, deleted.status_code)
            self.assertTrue(deleted.json()["deleted"])
            self.assertEqual("helper-cat", deleted.json()["name"])
            self.assertFalse(role_file.exists())

            self.assertEqual(200, current.status_code)
            self.assertEqual("default", current.json()["role_name"])

            self.assertEqual(200, listed_after_delete.status_code)
            self.assertEqual(["default"], [item["name"] for item in listed_after_delete.json()])

    def test_session_endpoints_support_chinese_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            created_name = "项目讨论"
            renamed_name = "二号会话"

            with TestClient(app) as client:
                created = client.post("/api/sessions", json={"name": created_name})
                current = client.get("/api/sessions/current")
                detail = client.get(f"/api/sessions/{quote(created_name, safe='')}")
                renamed = client.patch(
                    f"/api/sessions/{quote(created_name, safe='')}",
                    json={"name": renamed_name},
                )
                renamed_detail = client.get(f"/api/sessions/{quote(renamed_name, safe='')}")

            self.assertEqual(200, created.status_code)
            self.assertEqual(created_name, created.json()["name"])
            self.assertTrue((workspace / ".echobot" / "sessions" / f"{renamed_name}.jsonl").exists())

            self.assertEqual(200, current.status_code)
            self.assertEqual(created_name, current.json()["name"])

            self.assertEqual(200, detail.status_code)
            self.assertEqual(created_name, detail.json()["name"])

            self.assertEqual(200, renamed.status_code)
            self.assertEqual(renamed_name, renamed.json()["name"])

            self.assertEqual(200, renamed_detail.status_code)
            self.assertEqual(renamed_name, renamed_detail.json()["name"])

    def test_role_endpoints_support_chinese_role_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            role_name = "助手猫娘"
            role_prompt = "# 助手猫娘\n\n用简洁中文回答。"
            role_path = quote(role_name, safe="")
            role_file = workspace / ".echobot" / "roles" / f"{role_name}.md"

            with TestClient(app) as client:
                created = client.post(
                    "/api/roles",
                    json={
                        "name": role_name,
                        "prompt": role_prompt,
                    },
                )
                detail = client.get(f"/api/roles/{role_path}")
                switched = client.put(
                    "/api/sessions/default/role",
                    json={"role_name": role_name},
                )
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "default",
                        "prompt": "ping",
                    },
                )
                deleted = client.delete(f"/api/roles/{role_path}")

            self.assertEqual(200, created.status_code)
            self.assertEqual(role_name, created.json()["name"])
            self.assertTrue(str(created.json()["source_path"]).endswith(f"{role_name}.md"))

            self.assertEqual(200, detail.status_code)
            self.assertEqual(role_prompt, detail.json()["prompt"])

            self.assertEqual(200, switched.status_code)
            self.assertEqual(role_name, switched.json()["role_name"])

            self.assertEqual(200, replied.status_code)
            self.assertEqual(role_name, replied.json()["role_name"])

            self.assertEqual(200, deleted.status_code)
            self.assertTrue(deleted.json()["deleted"])
            self.assertEqual(role_name, deleted.json()["name"])
            self.assertFalse(role_file.exists())

    def test_default_role_card_is_read_only_from_web_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                detail = client.get("/api/roles/default")
                updated = client.put(
                    "/api/roles/default",
                    json={"prompt": "# Default\n\nChanged."},
                )
                deleted = client.delete("/api/roles/default")

            self.assertEqual(200, detail.status_code)
            self.assertFalse(detail.json()["editable"])
            self.assertFalse(detail.json()["deletable"])
            self.assertEqual(400, updated.status_code)
            self.assertIn("Default role card cannot be modified", updated.json()["detail"])
            self.assertEqual(400, deleted.status_code)
            self.assertIn("Default role card cannot be modified", deleted.json()["detail"])

    def test_session_endpoint_can_rename_current_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                client.post("/api/sessions", json={"name": "demo"})
                client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "ping",
                    },
                )

                renamed = client.patch("/api/sessions/demo", json={"name": "demo-renamed"})
                current = client.get("/api/sessions/current")
                renamed_detail = client.get("/api/sessions/demo-renamed")
                missing = client.get("/api/sessions/demo")

            self.assertEqual(200, renamed.status_code)
            self.assertEqual("demo-renamed", renamed.json()["name"])
            self.assertEqual(2, len(renamed.json()["history"]))
            self.assertEqual(200, current.status_code)
            self.assertEqual("demo-renamed", current.json()["name"])
            self.assertEqual(200, renamed_detail.status_code)
            self.assertEqual("demo-renamed", renamed_detail.json()["name"])
            self.assertEqual(404, missing.status_code)

    def test_delete_session_endpoint_removes_route_session_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                asr_service_builder=build_test_asr_service,
            )

            route_key = "telegram__12345__deadbeef"

            with TestClient(app) as client:
                runtime = client.app.state.runtime
                route_session = runtime.route_session_store.create_session(
                    route_key,
                    title="Route chat",
                )
                runtime.context.session_store.load_or_create_session(
                    route_session.session_name,
                )
                runtime.context.agent_session_store.load_or_create_session(
                    route_session.session_name,
                )
                runtime.delivery_store.remember(
                    route_session.session_name,
                    ChannelAddress(channel="telegram", chat_id="12345"),
                    {"message_id": 9},
                )
                runtime.context.session_store.set_current_session(
                    route_session.session_name,
                )

                deleted = client.delete(
                    f"/api/sessions/{quote(route_session.session_name, safe='')}",
                )
                current_session = client.get("/api/sessions/current")

                replacement = runtime.route_session_store.get_current_session(route_key)

            self.assertEqual(200, deleted.status_code)
            self.assertTrue(deleted.json()["deleted"])
            self.assertNotEqual(route_session.session_name, replacement.session_name)
            self.assertFalse(
                (
                    workspace
                    / ".echobot"
                    / "sessions"
                    / f"{route_session.session_name}.jsonl"
                ).exists()
            )
            self.assertFalse(
                (
                    workspace
                    / ".echobot"
                    / "agent_sessions"
                    / f"{route_session.session_name}.jsonl"
                ).exists()
            )
            self.assertIsNone(
                runtime.delivery_store.get_session_target(route_session.session_name),
            )
            self.assertEqual(200, current_session.status_code)
            self.assertNotEqual(
                route_session.session_name,
                current_session.json()["name"],
            )

    def test_chat_endpoint_returns_job_for_agent_style_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                )

                self.assertEqual(200, replied.status_code)
                payload = replied.json()
                self.assertTrue(payload["delegated"])
                self.assertFalse(payload["completed"])
                self.assertEqual("running", payload["status"])
                self.assertEqual("working", payload["response"])
                self.assertTrue(payload["job_id"])

                job_id = payload["job_id"]
                final = None
                for _ in range(20):
                    final = client.get(f"/api/chat/jobs/{job_id}")
                    if final.json()["status"] != "running":
                        break
                    time.sleep(0.01)

                assert final is not None
            self.assertEqual(200, final.status_code)
            self.assertEqual("completed", final.json()["status"])
            self.assertEqual("done", final.json()["response"])
            self.assertEqual("done", final.json()["response_content"])

    def test_chat_endpoint_can_disable_agent_ack(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    delegated_ack_enabled=False,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                )

                self.assertEqual(200, replied.status_code)
                payload = replied.json()
                self.assertTrue(payload["delegated"])
                self.assertFalse(payload["completed"])
                self.assertEqual("running", payload["status"])
                self.assertEqual("", payload["response"])
                self.assertTrue(payload["job_id"])

                job_id = payload["job_id"]
                final = None
                for _ in range(20):
                    final = client.get(f"/api/chat/jobs/{job_id}")
                    if final.json()["status"] != "running":
                        break
                    time.sleep(0.01)

                detail = client.get("/api/sessions/demo")

            assert final is not None
            self.assertEqual(200, final.status_code)
            self.assertEqual("completed", final.json()["status"])
            self.assertEqual("done", final.json()["response"])
            self.assertEqual("done", final.json()["response_content"])
            self.assertEqual(200, detail.status_code)
            history_contents = [item["content"] for item in detail.json()["history"]]
            self.assertNotIn("working", history_contents)
            self.assertIn("done", history_contents)

    def test_chat_job_cancel_endpoint_stops_running_background_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_slow_agent_test_context,
            )

            with TestClient(app) as client:
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                )

                self.assertEqual(200, replied.status_code)
                job_id = replied.json()["job_id"]
                self.assertTrue(job_id)

                cancelled = client.post(f"/api/chat/jobs/{job_id}/cancel")
                final = client.get(f"/api/chat/jobs/{job_id}")
                detail = client.get("/api/sessions/demo")

            self.assertEqual(200, cancelled.status_code)
            self.assertEqual("cancelled", cancelled.json()["status"])
            self.assertEqual(
                "后台任务已停止。",
                cancelled.json()["response"],
            )

            self.assertEqual(200, final.status_code)
            self.assertEqual("cancelled", final.json()["status"])
            self.assertEqual(
                "后台任务已停止。",
                final.json()["response"],
            )

            self.assertEqual(200, detail.status_code)
            history_contents = [item["content"] for item in detail.json()["history"]]
            self.assertIn("working", history_contents)
            self.assertIn("后台任务已停止。", history_contents)

    def test_chat_job_list_endpoint_returns_latest_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                first = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                )
                second = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                )
                jobs = client.get("/api/chat/jobs?session_name=demo&limit=10")

            self.assertEqual(200, first.status_code)
            self.assertEqual(200, second.status_code)
            self.assertEqual(200, jobs.status_code)
            payload = jobs.json()
            self.assertEqual(2, len(payload["jobs"]))
            self.assertEqual("demo", payload["jobs"][0]["session_name"])
            self.assertIn("prompt", payload["jobs"][0])
            self.assertIn("attempt", payload["jobs"][0])
            self.assertIn("started_at", payload["jobs"][0])

    def test_chat_job_retry_endpoint_starts_new_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_slow_agent_test_context,
            )

            with TestClient(app) as client:
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                )
                original_job_id = replied.json()["job_id"]
                cancelled = client.post(f"/api/chat/jobs/{original_job_id}/cancel")
                retried = client.post(f"/api/chat/jobs/{original_job_id}/retry")

                self.assertEqual(200, cancelled.status_code)
                self.assertEqual(200, retried.status_code)
                self.assertNotEqual(original_job_id, retried.json()["job_id"])
                self.assertEqual("running", retried.json()["status"])

                retried_job_id = retried.json()["job_id"]
                final = None
                for _ in range(300):
                    final = client.get(f"/api/chat/jobs/{retried_job_id}")
                    if final.json()["status"] != "running":
                        break
                    time.sleep(0.01)

            assert final is not None
            self.assertEqual(200, final.status_code)
            self.assertEqual("completed", final.json()["status"])
            self.assertEqual(2, final.json()["attempt"])
            self.assertEqual(original_job_id, final.json()["retry_of_job_id"])

    def test_chat_job_trace_endpoint_returns_recorded_trace_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                replied = client.post(
                    "/api/chat",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                )

                self.assertEqual(200, replied.status_code)
                job_id = replied.json()["job_id"]
                self.assertTrue(job_id)

                trace_response = None
                for _ in range(100):
                    trace_response = client.get(f"/api/chat/jobs/{job_id}/trace")
                    payload = trace_response.json()
                    events = payload["events"]
                    if (
                        payload["status"] == "completed"
                        and events
                        and events[-1]["event"] == "turn_completed"
                    ):
                        break
                    time.sleep(0.01)

            assert trace_response is not None
            self.assertEqual(200, trace_response.status_code)
            payload = trace_response.json()
            self.assertEqual(job_id, payload["job_id"])
            self.assertEqual("completed", payload["status"])
            self.assertGreaterEqual(len(payload["events"]), 3)
            self.assertEqual("turn_started", payload["events"][0]["event"])
            self.assertEqual("assistant_message", payload["events"][1]["event"])
            self.assertEqual("turn_completed", payload["events"][-1]["event"])
            self.assertEqual(
                "pong",
                payload["events"][-1]["final_message"]["content"],
            )

    def test_chat_stream_endpoint_streams_roleplay_chunks_and_final_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                with client.stream(
                    "POST",
                    "/api/chat/stream",
                    json={
                        "session_name": "demo",
                        "prompt": "ping",
                    },
                ) as response:
                    lines = [
                        line if isinstance(line, str) else line.decode("utf-8")
                        for line in response.iter_lines()
                        if line
                    ]

            self.assertEqual(200, response.status_code)
            events = [json.loads(line) for line in lines]
            self.assertEqual("chunk", events[0]["type"])
            self.assertEqual("chunk", events[1]["type"])
            self.assertEqual("po", events[0]["delta"])
            self.assertEqual("ng", events[1]["delta"])
            self.assertEqual("done", events[-1]["type"])
            self.assertEqual("pong", events[-1]["response"])
            self.assertEqual("pong", events[-1]["response_content"])
            self.assertFalse(events[-1]["delegated"])
            self.assertTrue(events[-1]["completed"])

    def test_chat_stream_endpoint_streams_agent_ack_before_background_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                with client.stream(
                    "POST",
                    "/api/chat/stream",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                ) as response:
                    lines = [
                        line if isinstance(line, str) else line.decode("utf-8")
                        for line in response.iter_lines()
                        if line
                    ]

                done_event = json.loads(lines[-1])
                final_job = None
                for _ in range(20):
                    final_job = client.get(f"/api/chat/jobs/{done_event['job_id']}")
                    if final_job.json()["status"] != "running":
                        break
                    time.sleep(0.01)

            self.assertEqual(200, response.status_code)
            events = [json.loads(line) for line in lines]
            self.assertEqual("chunk", events[0]["type"])
            self.assertEqual("done", done_event["type"])
            self.assertTrue(done_event["delegated"])
            self.assertFalse(done_event["completed"])
            self.assertEqual("working", done_event["response"])
            self.assertTrue(done_event["job_id"])

            assert final_job is not None
            self.assertEqual(200, final_job.status_code)
            self.assertEqual("completed", final_job.json()["status"])
            self.assertEqual("done", final_job.json()["response"])
            self.assertEqual("done", final_job.json()["response_content"])

    def test_chat_stream_disconnect_after_ack_still_runs_background_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_slow_ack_test_context,
            )

            with TestClient(app) as client:
                with client.stream(
                    "POST",
                    "/api/chat/stream",
                    json={
                        "session_name": "demo",
                        "prompt": "Please set a cron reminder",
                    },
                ) as response:
                    first_line = None
                    for line in response.iter_lines():
                        if not line:
                            continue
                        first_line = (
                            line
                            if isinstance(line, str)
                            else line.decode("utf-8")
                        )
                        break

                self.assertEqual(200, response.status_code)
                self.assertIsNotNone(first_line)
                first_event = json.loads(first_line)
                self.assertEqual("chunk", first_event["type"])
                self.assertEqual("working", first_event["delta"])

                detail = None
                for _ in range(30):
                    detail = client.get("/api/sessions/demo")
                    contents = [
                        item["content"]
                        for item in detail.json()["history"]
                    ]
                    if "done" in contents:
                        break
                    time.sleep(0.01)

            assert detail is not None
            self.assertEqual(200, detail.status_code)
            history_contents = [item["content"] for item in detail.json()["history"]]
            self.assertIn("working", history_contents)
            self.assertIn("done", history_contents)

    def test_cron_endpoints_return_status_and_job_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_cron_jobs(workspace)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                status = client.get("/api/cron/status")
                jobs = client.get("/api/cron/jobs?include_disabled=true")

            self.assertEqual(200, status.status_code)
            self.assertTrue(status.json()["enabled"])
            self.assertEqual(2, status.json()["jobs"])
            self.assertTrue(status.json()["next_run_at"])

            self.assertEqual(200, jobs.status_code)
            payload = jobs.json()
            self.assertEqual(2, len(payload["jobs"]))
            jobs_by_id = {
                item["id"]: item
                for item in payload["jobs"]
            }
            self.assertEqual("Morning summary", jobs_by_id["job_enabled"]["name"])
            self.assertEqual("every 3600s", jobs_by_id["job_enabled"]["schedule"])
            self.assertEqual("agent", jobs_by_id["job_enabled"]["payload_kind"])
            self.assertTrue(jobs_by_id["job_enabled"]["enabled"])
            self.assertEqual("Disabled reminder", jobs_by_id["job_disabled"]["name"])
            self.assertEqual("error", jobs_by_id["job_disabled"]["last_status"])
            self.assertEqual("network timeout", jobs_by_id["job_disabled"]["last_error"])

    def test_cron_delete_endpoint_removes_job_and_returns_not_found_afterwards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_cron_jobs(workspace)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            with TestClient(app) as client:
                deleted = client.delete("/api/cron/jobs/job_enabled")
                jobs = client.get("/api/cron/jobs?include_disabled=true")
                missing = client.delete("/api/cron/jobs/job_enabled")

            self.assertEqual(200, deleted.status_code)
            self.assertEqual(
                {
                    "deleted": True,
                    "job_id": "job_enabled",
                },
                deleted.json(),
            )

            self.assertEqual(200, jobs.status_code)
            payload = jobs.json()
            self.assertEqual(1, len(payload["jobs"]))
            self.assertEqual("job_disabled", payload["jobs"][0]["id"])

            saved = json.loads(
                (workspace / ".echobot" / "cron" / "jobs.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(1, len(saved["jobs"]))
            self.assertEqual("job_disabled", saved["jobs"][0]["id"])

            self.assertEqual(404, missing.status_code)
            self.assertEqual("Cron job not found: job_enabled", missing.json()["detail"])

    def test_heartbeat_endpoint_returns_content_and_allows_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_heartbeat_file(
                workspace,
                "# HEARTBEAT.md\n\n- [ ] Check inbox\n",
            )
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
            )

            updated_content = "# HEARTBEAT.md\n\n- [ ] Review roadmap\n"

            with TestClient(app) as client:
                heartbeat = client.get("/api/heartbeat")
                saved = client.put(
                    "/api/heartbeat",
                    json={"content": updated_content},
                )

            self.assertEqual(200, heartbeat.status_code)
            self.assertTrue(heartbeat.json()["enabled"])
            self.assertEqual(60, heartbeat.json()["interval_seconds"])
            self.assertEqual(
                str((workspace / ".echobot" / "HEARTBEAT.md").resolve()),
                heartbeat.json()["file_path"],
            )
            self.assertEqual("# HEARTBEAT.md\n\n- [ ] Check inbox\n", heartbeat.json()["content"])
            self.assertTrue(heartbeat.json()["has_meaningful_content"])

            self.assertEqual(200, saved.status_code)
            self.assertEqual(updated_content, saved.json()["content"])
            self.assertTrue(saved.json()["has_meaningful_content"])
            self.assertEqual(
                updated_content,
                (workspace / ".echobot" / "HEARTBEAT.md").read_text(encoding="utf-8"),
            )

    def test_web_console_routes_expose_static_ui_and_live2d_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                page = client.get("/web")
                config = client.get("/api/web/config")

                self.assertEqual(200, page.status_code)
                self.assertIn('id="model-select"', page.text)
                self.assertIn('id="session-sidebar-toggle"', page.text)
                self.assertIn('id="page-resizer"', page.text)
                self.assertIn('id="session-list"', page.text)
                self.assertIn('id="record-button"', page.text)
                self.assertIn('id="always-listen-checkbox"', page.text)
                self.assertIn('id="role-select"', page.text)
                self.assertIn('id="stop-agent-button"', page.text)
                self.assertNotIn('id="session-create-button"', page.text)
                self.assertNotIn('id="role-editor"', page.text)
                self.assertIn('id="tts-provider-select"', page.text)
                self.assertIn('id="asr-provider-select"', page.text)
                self.assertIn('id="route-mode-select"', page.text)
                self.assertIn('class="console-admin-handoff"', page.text)
                self.assertIn('id="console-advanced-overrides-panel"', page.text)
                self.assertIn('href="/admin/sessions"', page.text)
                self.assertIn('href="/admin/characters"', page.text)
                self.assertIn('href="/admin/models"', page.text)
                self.assertIn('href="/admin/voice-models"', page.text)
                self.assertIn('href="/admin/live2d"', page.text)
                self.assertIn('id="runtime-panel"', page.text)
                self.assertIn('id="runtime-reset-button"', page.text)
                self.assertIn('id="delegated-ack-checkbox"', page.text)
                self.assertIn('id="shell-safety-mode-select"', page.text)
                self.assertIn('id="file-write-enabled-checkbox"', page.text)
                self.assertIn('id="cron-mutation-enabled-checkbox"', page.text)
                self.assertIn('id="web-private-network-enabled-checkbox"', page.text)
                self.assertIn('id="heartbeat-panel"', page.text)
                self.assertIn('id="heartbeat-input"', page.text)
                self.assertIn('id="heartbeat-save-button"', page.text)
                self.assertIn('id="agent-trace-panel"', page.text)
                self.assertIn('id="agent-trace-events"', page.text)
                self.assertIn('id="live2d-panel"', page.text)
                self.assertIn('id="live2d-drawer"', page.text)
                self.assertIn('id="live2d-drawer-toggle"', page.text)
                self.assertIn('id="live2d-hotkeys-checkbox"', page.text)
                self.assertIn('id="live2d-upload-button"', page.text)
                self.assertIn('id="live2d-upload-input"', page.text)
                self.assertIn('id="stage-background-select"', page.text)
                self.assertIn('id="stage-background-upload-button"', page.text)
                self.assertIn('id="stage-background-position-x-input"', page.text)
                self.assertIn('id="stage-background-position-y-input"', page.text)
                self.assertIn('id="stage-background-scale-input"', page.text)
                self.assertIn('id="stage-background-transform-reset-button"', page.text)
                self.assertIn('id="stage-effects-particles-enabled-checkbox"', page.text)
                self.assertIn('id="stage-effects-particle-density-input"', page.text)
                self.assertIn('id="stage-effects-particle-opacity-input"', page.text)
                self.assertIn('id="stage-effects-particle-size-input"', page.text)
                self.assertIn('id="stage-effects-particle-speed-input"', page.text)
                self.assertIn('id="window-file-drop-overlay"', page.text)
                self.assertIn('id="message-image-dialog"', page.text)
                self.assertIn('id="message-image-dialog-image"', page.text)
                self.assertNotIn('id="message-image-dialog-link"', page.text)
                self.assertIn("EchoBot Web Console", page.text)
                self.assertIn('data-i18n-key="console.heartbeatJobs"', page.text)
                self.assertIn("HEARTBEAT Jobs", page.text)
                self.assertIn('data-i18n-key="console.cronJobs"', page.text)
                self.assertIn("CRON Jobs", page.text)

                self.assertEqual(200, config.status_code)
                payload = config.json()
                self.assertEqual("default", payload["session_name"])
                self.assertEqual("auto", payload["route_mode"])
                self.assertTrue(payload["runtime"]["delegated_ack_enabled"])
                self.assertEqual(
                    DEFAULT_SHELL_SAFETY_MODE,
                    payload["runtime"]["shell_safety_mode"],
                )
                self.assertTrue(payload["runtime"]["file_write_enabled"])
                self.assertTrue(payload["runtime"]["cron_mutation_enabled"])
                self.assertFalse(payload["runtime"]["web_private_network_enabled"])
                self.assertEqual("default", payload["stage"]["default_background_key"])
                self.assertEqual("default", payload["stage"]["backgrounds"][0]["key"])
                self.assertEqual("不使用背景", payload["stage"]["backgrounds"][0]["label"])
                builtin_background = next(
                    (
                        item
                        for item in payload["stage"]["backgrounds"]
                        if item["kind"] == "builtin"
                    ),
                    None,
                )
                self.assertIsNotNone(builtin_background)
                self.assertTrue(payload["asr"]["available"])
                self.assertEqual("ready", payload["asr"]["state"])
                self.assertEqual(16000, payload["asr"]["sample_rate"])
                self.assertEqual("fake-asr", payload["asr"]["selected_asr_provider"])
                self.assertTrue(
                    any(item["name"] == "backup-asr" for item in payload["asr"]["asr_providers"])
                )
                self.assertEqual("edge", payload["tts"]["default_provider"])
                self.assertEqual("zh-CN-XiaoxiaoNeural", payload["tts"]["default_voices"]["edge"])
                self.assertEqual("zf_001", payload["tts"]["default_voices"]["kokoro"])
                self.assertTrue(
                    any(item["name"] == "kokoro" for item in payload["tts"]["providers"])
                )
                self.assertTrue(payload["live2d"]["available"])
                self.assertEqual("workspace", payload["live2d"]["source"])
                self.assertEqual("兔兔 ", payload["live2d"]["model_name"])
                self.assertIn("ParamMouthOpenY", payload["live2d"]["lip_sync_parameter_ids"])
                self.assertEqual("ParamMouthForm", payload["live2d"]["mouth_form_parameter_id"])
                self.assertIn("%E5%85%94%E5%85%94", payload["live2d"]["model_url"])
                self.assertTrue(payload["live2d"]["selection_key"].startswith("workspace:"))
                self.assertTrue(
                    any(
                        item["source"] == "workspace"
                        and item["directory_name"] == "兔兔"
                        for item in payload["live2d"]["models"]
                    )
                )
                self.assertTrue(
                    any(item["source"] == "builtin" for item in payload["live2d"]["models"])
                )

                model_response = client.get(payload["live2d"]["model_url"])
                builtin_background_response = client.get(builtin_background["url"])
                texture_response = client.get(
                    "/api/web/live2d/workspace/%E5%85%94%E5%85%94/%E5%85%94%E5%85%94%20.4096/texture_00.png",
                )

                self.assertEqual(200, model_response.status_code)
                self.assertEqual(200, builtin_background_response.status_code)
                self.assertGreater(len(builtin_background_response.content), 0)
                self.assertEqual(200, texture_response.status_code)
                self.assertIn("DisplayInfo", model_response.text)

    def test_web_console_runtime_toggle_updates_config_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            settings_path = workspace / ".echobot" / "runtime_settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps(
                    {
                        "delegated_ack_enabled": True,
                        "shell_safety_mode": "danger-full-access",
                        "file_write_enabled": True,
                        "cron_mutation_enabled": True,
                        "web_private_network_enabled": False,
                        "future_setting": "keep-me",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                updated = client.patch(
                    "/api/web/runtime",
                    json={
                        "delegated_ack_enabled": False,
                        "shell_safety_mode": "read-only",
                        "file_write_enabled": False,
                        "cron_mutation_enabled": False,
                        "web_private_network_enabled": True,
                    },
                )
                config = client.get("/api/web/config")

            self.assertEqual(200, updated.status_code)
            self.assertFalse(updated.json()["delegated_ack_enabled"])
            self.assertEqual("read-only", updated.json()["shell_safety_mode"])
            self.assertFalse(updated.json()["file_write_enabled"])
            self.assertFalse(updated.json()["cron_mutation_enabled"])
            self.assertTrue(updated.json()["web_private_network_enabled"])
            self.assertEqual(200, config.status_code)
            self.assertFalse(config.json()["runtime"]["delegated_ack_enabled"])
            self.assertEqual("read-only", config.json()["runtime"]["shell_safety_mode"])
            self.assertFalse(config.json()["runtime"]["file_write_enabled"])
            self.assertFalse(config.json()["runtime"]["cron_mutation_enabled"])
            self.assertTrue(config.json()["runtime"]["web_private_network_enabled"])

            self.assertTrue(settings_path.exists())
            settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    "delegated_ack_enabled": False,
                    "shell_safety_mode": "read-only",
                    "file_write_enabled": False,
                    "cron_mutation_enabled": False,
                    "web_private_network_enabled": True,
                    "future_setting": "keep-me",
                },
                settings_payload,
            )

            restarted_app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(restarted_app) as client:
                restarted_config = client.get("/api/web/config")

            self.assertEqual(200, restarted_config.status_code)
            self.assertFalse(restarted_config.json()["runtime"]["delegated_ack_enabled"])
            self.assertEqual(
                "read-only",
                restarted_config.json()["runtime"]["shell_safety_mode"],
            )
            self.assertFalse(restarted_config.json()["runtime"]["file_write_enabled"])
            self.assertFalse(restarted_config.json()["runtime"]["cron_mutation_enabled"])
            self.assertTrue(restarted_config.json()["runtime"]["web_private_network_enabled"])

    def test_web_console_runtime_patch_updates_only_requested_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            settings_path = workspace / ".echobot" / "runtime_settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps(
                    {
                        "delegated_ack_enabled": False,
                        "shell_safety_mode": "read-only",
                        "file_write_enabled": True,
                        "cron_mutation_enabled": False,
                        "web_private_network_enabled": True,
                        "future_setting": "keep-me",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                updated = client.patch(
                    "/api/web/runtime",
                    json={"file_write_enabled": False},
                )
                config = client.get("/api/web/config")

            self.assertEqual(200, updated.status_code)
            self.assertFalse(updated.json()["delegated_ack_enabled"])
            self.assertEqual("read-only", updated.json()["shell_safety_mode"])
            self.assertFalse(updated.json()["file_write_enabled"])
            self.assertFalse(updated.json()["cron_mutation_enabled"])
            self.assertTrue(updated.json()["web_private_network_enabled"])

            self.assertEqual(200, config.status_code)
            self.assertFalse(config.json()["runtime"]["delegated_ack_enabled"])
            self.assertEqual("read-only", config.json()["runtime"]["shell_safety_mode"])
            self.assertFalse(config.json()["runtime"]["file_write_enabled"])
            self.assertFalse(config.json()["runtime"]["cron_mutation_enabled"])
            self.assertTrue(config.json()["runtime"]["web_private_network_enabled"])

            settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    "delegated_ack_enabled": False,
                    "shell_safety_mode": "read-only",
                    "file_write_enabled": False,
                    "cron_mutation_enabled": False,
                    "web_private_network_enabled": True,
                    "future_setting": "keep-me",
                },
                settings_payload,
            )

    def test_web_console_runtime_reset_clears_overrides_and_restores_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            settings_path = workspace / ".echobot" / "runtime_settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps(
                    {
                        "delegated_ack_enabled": True,
                        "shell_safety_mode": "read-only",
                        "file_write_enabled": False,
                        "cron_mutation_enabled": False,
                        "web_private_network_enabled": True,
                        "future_setting": "keep-me",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            runtime_options = RuntimeOptions(
                workspace=workspace,
                delegated_ack_enabled=False,
                no_tools=True,
                no_skills=True,
                no_memory=True,
                no_heartbeat=True,
            )
            app = create_app(
                runtime_options=runtime_options,
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                reset = client.post("/api/web/runtime/reset")
                config = client.get("/api/web/config")

            self.assertEqual(200, reset.status_code)
            self.assertFalse(reset.json()["delegated_ack_enabled"])
            self.assertEqual(DEFAULT_SHELL_SAFETY_MODE, reset.json()["shell_safety_mode"])
            self.assertTrue(reset.json()["file_write_enabled"])
            self.assertTrue(reset.json()["cron_mutation_enabled"])
            self.assertFalse(reset.json()["web_private_network_enabled"])

            self.assertEqual(200, config.status_code)
            self.assertFalse(config.json()["runtime"]["delegated_ack_enabled"])
            self.assertEqual(
                DEFAULT_SHELL_SAFETY_MODE,
                config.json()["runtime"]["shell_safety_mode"],
            )
            self.assertTrue(config.json()["runtime"]["file_write_enabled"])
            self.assertTrue(config.json()["runtime"]["cron_mutation_enabled"])
            self.assertFalse(config.json()["runtime"]["web_private_network_enabled"])

            settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    "future_setting": "keep-me",
                },
                settings_payload,
            )

            restarted_app = create_app(
                runtime_options=runtime_options,
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(restarted_app) as client:
                restarted_config = client.get("/api/web/config")

            self.assertEqual(200, restarted_config.status_code)
            self.assertFalse(restarted_config.json()["runtime"]["delegated_ack_enabled"])
            self.assertEqual(
                DEFAULT_SHELL_SAFETY_MODE,
                restarted_config.json()["runtime"]["shell_safety_mode"],
            )
            self.assertTrue(restarted_config.json()["runtime"]["file_write_enabled"])
            self.assertTrue(restarted_config.json()["runtime"]["cron_mutation_enabled"])
            self.assertFalse(
                restarted_config.json()["runtime"]["web_private_network_enabled"]
            )

    def test_web_console_asr_provider_switch_updates_config_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            settings_path = workspace / ".echobot" / "runtime_settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps(
                    {
                        "delegated_ack_enabled": True,
                        "future_setting": "keep-me",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                updated = client.patch(
                    "/api/web/asr/provider",
                    json={
                        "provider": "backup-asr",
                    },
                )
                config = client.get("/api/web/config")

            self.assertEqual(200, updated.status_code)
            self.assertEqual("backup-asr", updated.json()["selected_asr_provider"])
            self.assertEqual(200, config.status_code)
            self.assertEqual("backup-asr", config.json()["asr"]["selected_asr_provider"])

            self.assertTrue(settings_path.exists())
            settings_payload = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {
                    "delegated_ack_enabled": True,
                    "selected_asr_provider": "backup-asr",
                    "future_setting": "keep-me",
                },
                settings_payload,
            )

            restarted_app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(restarted_app) as client:
                restarted_config = client.get("/api/web/config")

            self.assertEqual(200, restarted_config.status_code)
            self.assertEqual("backup-asr", restarted_config.json()["asr"]["selected_asr_provider"])

    def test_web_console_stage_background_upload_and_asset_routes_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                uploaded = client.post(
                    "/api/web/stage/backgrounds",
                    files={
                        "image": ("sunset.png", b"fake-image-bytes", "image/png"),
                    },
                )
                config = client.get("/api/web/config")

                self.assertEqual(200, uploaded.status_code)
                uploaded_payload = uploaded.json()
                self.assertTrue(
                    any(item["label"] == "sunset" for item in uploaded_payload["backgrounds"])
                )

                background_item = next(
                    item
                    for item in uploaded_payload["backgrounds"]
                    if item["label"] == "sunset"
                )
                self.assertEqual("uploaded", background_item["kind"])
                asset_response = client.get(background_item["url"])

                self.assertEqual(200, asset_response.status_code)
                self.assertEqual(b"fake-image-bytes", asset_response.content)
                self.assertEqual(200, config.status_code)
                self.assertTrue(
                    any(item["label"] == "sunset" for item in config.json()["stage"]["backgrounds"])
                )

    def test_web_console_live2d_folder_upload_and_asset_routes_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            model_payload = {
                "Version": 3,
                "FileReferences": {
                    "Moc": "cat.moc3",
                    "Textures": [
                        "textures/texture_00.png",
                    ],
                    "DisplayInfo": "cat.cdi3.json",
                },
            }
            display_info_payload = {
                "Version": 3,
                "Parameters": [
                    {"Id": "ParamMouthOpenY", "Name": "Mouth Open"},
                    {"Id": "ParamMouthForm", "Name": "Mouth Form"},
                ],
            }

            with TestClient(app) as client:
                uploaded = client.post(
                    "/api/web/live2d",
                    files=[
                        (
                            "files",
                            ("cat.model3.json", json.dumps(model_payload, ensure_ascii=False), "application/json"),
                        ),
                        ("relative_paths", (None, "cat_model/runtime/cat.model3.json")),
                        (
                            "files",
                            ("cat.cdi3.json", json.dumps(display_info_payload, ensure_ascii=False), "application/json"),
                        ),
                        ("relative_paths", (None, "cat_model/runtime/cat.cdi3.json")),
                        ("files", ("cat.moc3", b"fake-cat-moc3", "application/octet-stream")),
                        ("relative_paths", (None, "cat_model/runtime/cat.moc3")),
                        ("files", ("texture_00.png", b"fake-cat-png", "image/png")),
                        ("relative_paths", (None, "cat_model/runtime/textures/texture_00.png")),
                        ("files", ("README.txt", "ignore-me", "text/plain")),
                        ("relative_paths", (None, "cat_model/README.txt")),
                    ],
                )
                config = client.get("/api/web/config")

                self.assertEqual(200, uploaded.status_code)
                uploaded_payload = uploaded.json()
                uploaded_model = next(
                    item
                    for item in uploaded_payload["models"]
                    if item["selection_key"] == "workspace:cat_model/runtime/cat.model3.json"
                )

                self.assertEqual("workspace", uploaded_model["source"])
                self.assertEqual("cat_model", uploaded_model["directory_name"])
                self.assertEqual("cat", uploaded_model["model_name"])
                self.assertEqual(["ParamMouthOpenY"], uploaded_model["lip_sync_parameter_ids"])

                model_response = client.get(uploaded_model["model_url"])
                texture_response = client.get(
                    f"/api/web/live2d/workspace/{quote('cat_model/runtime/textures/texture_00.png')}",
                )

                self.assertEqual(200, model_response.status_code)
                self.assertIn("DisplayInfo", model_response.text)
                self.assertEqual(200, texture_response.status_code)
                self.assertEqual(b"fake-cat-png", texture_response.content)
                self.assertEqual(200, config.status_code)
                self.assertTrue(
                    any(
                        item["selection_key"] == "workspace:cat_model/runtime/cat.model3.json"
                        for item in config.json()["live2d"]["models"]
                    )
                )

    def test_web_console_discovers_live2d_controls_from_vtube_json_and_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_vtube_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                config = client.get("/api/web/config")

            self.assertEqual(200, config.status_code)
            payload = config.json()["live2d"]
            self.assertEqual("workspace", payload["source"])
            self.assertEqual("yumi", payload["directory_name"])
            self.assertTrue(payload["annotations_writable"])
            self.assertEqual(
                ["smile.exp3.json", "sad.exp3.json"],
                [item["file"] for item in payload["expressions"]],
            )
            self.assertEqual(
                "默认笑脸",
                next(item["note"] for item in payload["expressions"] if item["file"] == "smile.exp3.json"),
            )
            self.assertEqual(
                ["wave.motion3.json", "jump.motion3.json"],
                [item["file"] for item in payload["motions"]],
            )
            self.assertEqual(
                ["hk_exp_smile", "hk_motion_wave", "hk_clear"],
                [item["hotkey_id"] for item in payload["hotkeys"]],
            )
            self.assertEqual(
                ["alt", "digit1"],
                payload["hotkeys"][0]["shortcut_tokens"],
            )
            self.assertEqual("Ctrl + F3", payload["hotkeys"][1]["shortcut_label"])
            self.assertTrue(payload["hotkeys"][2]["supported"])

    def test_web_console_patches_model3_json_with_discovered_live2d_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_vtube_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                config = client.get("/api/web/config")
                model_response = client.get(config.json()["live2d"]["model_url"])

            self.assertEqual(200, config.status_code)
            self.assertEqual(200, model_response.status_code)
            patched_model = model_response.json()
            self.assertEqual(
                ["smile.exp3.json", "sad.exp3.json"],
                [item["File"] for item in patched_model["FileReferences"]["Expressions"]],
            )
            self.assertIn("EchoBotIdle", patched_model["FileReferences"]["Motions"])
            self.assertIn("EchoBotAuto", patched_model["FileReferences"]["Motions"])
            self.assertEqual(
                "wave.motion3.json",
                patched_model["FileReferences"]["Motions"]["EchoBotIdle"][0]["File"],
            )
            self.assertEqual(
                "jump.motion3.json",
                patched_model["FileReferences"]["Motions"]["EchoBotAuto"][0]["File"],
            )

    def test_web_console_can_save_live2d_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_vtube_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                config = client.get("/api/web/config")
                selection_key = config.json()["live2d"]["selection_key"]
                expression_saved = client.patch(
                    "/api/web/live2d/annotations",
                    json={
                        "selection_key": selection_key,
                        "kind": "expression",
                        "file": "sad.exp3.json",
                        "note": "悲伤播报",
                    },
                )
                motion_saved = client.patch(
                    "/api/web/live2d/annotations",
                    json={
                        "selection_key": selection_key,
                        "kind": "motion",
                        "file": "jump.motion3.json",
                        "note": "高兴时播放",
                    },
                )
                refreshed = client.get("/api/web/config")

            self.assertEqual(200, expression_saved.status_code)
            self.assertEqual(200, motion_saved.status_code)
            annotations_path = (
                workspace
                / ".echobot"
                / "live2d"
                / "yumi"
                / "echobot.live2d.json"
            )
            annotations_payload = json.loads(annotations_path.read_text(encoding="utf-8"))
            self.assertEqual("悲伤播报", annotations_payload["expressions"]["sad.exp3.json"])
            self.assertEqual("高兴时播放", annotations_payload["motions"]["jump.motion3.json"])
            self.assertEqual(
                "悲伤播报",
                next(
                    item["note"]
                    for item in refreshed.json()["live2d"]["expressions"]
                    if item["file"] == "sad.exp3.json"
                ),
            )
            self.assertEqual(
                "高兴时播放",
                next(
                    item["note"]
                    for item in refreshed.json()["live2d"]["motions"]
                    if item["file"] == "jump.motion3.json"
                ),
            )

    def test_web_console_can_save_live2d_hotkeys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_vtube_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                config = client.get("/api/web/config")
                selection_key = config.json()["live2d"]["selection_key"]
                hotkey_saved = client.patch(
                    "/api/web/live2d/hotkeys",
                    json={
                        "selection_key": selection_key,
                        "hotkey_key": "hk_motion_wave",
                        "shortcut_tokens": ["Shift", "N2"],
                    },
                )
                hotkey_cleared = client.patch(
                    "/api/web/live2d/hotkeys",
                    json={
                        "selection_key": selection_key,
                        "hotkey_key": "hk_clear",
                        "shortcut_tokens": [],
                    },
                )
                refreshed = client.get("/api/web/config")

            self.assertEqual(200, hotkey_saved.status_code)
            self.assertEqual(
                ["shift", "digit2"],
                hotkey_saved.json()["shortcut_tokens"],
            )
            self.assertEqual("Shift + 2", hotkey_saved.json()["shortcut_label"])
            self.assertEqual(200, hotkey_cleared.status_code)
            self.assertEqual([], hotkey_cleared.json()["shortcut_tokens"])
            self.assertEqual("Unassigned", hotkey_cleared.json()["shortcut_label"])

            annotations_path = (
                workspace
                / ".echobot"
                / "live2d"
                / "yumi"
                / "echobot.live2d.json"
            )
            annotations_payload = json.loads(annotations_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ["shift", "digit2"],
                annotations_payload["hotkeys"]["hk_motion_wave"]["shortcut_tokens"],
            )
            self.assertEqual(
                [],
                annotations_payload["hotkeys"]["hk_clear"]["shortcut_tokens"],
            )
            refreshed_hotkeys = {
                item["hotkey_key"]: item
                for item in refreshed.json()["live2d"]["hotkeys"]
            }
            self.assertEqual(
                ["shift", "digit2"],
                refreshed_hotkeys["hk_motion_wave"]["shortcut_tokens"],
            )
            self.assertEqual(
                "Shift + 2",
                refreshed_hotkeys["hk_motion_wave"]["shortcut_label"],
            )
            self.assertEqual(
                [],
                refreshed_hotkeys["hk_clear"]["shortcut_tokens"],
            )

    def test_web_console_can_restore_live2d_hotkey_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_vtube_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                config = client.get("/api/web/config")
                selection_key = config.json()["live2d"]["selection_key"]
                saved = client.patch(
                    "/api/web/live2d/hotkeys",
                    json={
                        "selection_key": selection_key,
                        "hotkey_key": "hk_motion_wave",
                        "shortcut_tokens": ["Shift", "N2"],
                    },
                )
                restored = client.patch(
                    "/api/web/live2d/hotkeys",
                    json={
                        "selection_key": selection_key,
                        "hotkey_key": "hk_motion_wave",
                        "restore_default": True,
                    },
                )
                refreshed = client.get("/api/web/config")

            self.assertEqual(200, saved.status_code)
            self.assertEqual(200, restored.status_code)
            self.assertEqual(
                ["control", "f3"],
                restored.json()["shortcut_tokens"],
            )
            self.assertEqual("Ctrl + F3", restored.json()["shortcut_label"])

            annotations_path = (
                workspace
                / ".echobot"
                / "live2d"
                / "yumi"
                / "echobot.live2d.json"
            )
            annotations_payload = json.loads(annotations_path.read_text(encoding="utf-8"))
            self.assertNotIn("hk_motion_wave", annotations_payload["hotkeys"])

            refreshed_hotkeys = {
                item["hotkey_key"]: item
                for item in refreshed.json()["live2d"]["hotkeys"]
            }
            self.assertEqual(
                ["control", "f3"],
                refreshed_hotkeys["hk_motion_wave"]["shortcut_tokens"],
            )
            self.assertEqual(
                "Ctrl + F3",
                refreshed_hotkeys["hk_motion_wave"]["shortcut_label"],
            )

    def test_web_console_isolates_live2d_annotations_per_runtime_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_split_runtime_live2d_models(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                config = client.get("/api/web/config")
                workspace_models = [
                    item
                    for item in config.json()["live2d"]["models"]
                    if item["source"] == "workspace"
                ]
                alpha_model = next(
                    item
                    for item in workspace_models
                    if item["model_name"] == "alpha"
                )
                beta_model = next(
                    item
                    for item in workspace_models
                    if item["model_name"] == "beta"
                )

                alpha_saved = client.patch(
                    "/api/web/live2d/annotations",
                    json={
                        "selection_key": alpha_model["selection_key"],
                        "kind": "expression",
                        "file": "smile.exp3.json",
                        "note": "alpha custom note",
                    },
                )
                beta_hotkey_saved = client.patch(
                    "/api/web/live2d/hotkeys",
                    json={
                        "selection_key": beta_model["selection_key"],
                        "hotkey_key": "hk_smile",
                        "shortcut_tokens": ["Alt", "Digit9"],
                    },
                )
                refreshed = client.get("/api/web/config")

            self.assertEqual(200, alpha_saved.status_code)
            self.assertEqual(200, beta_hotkey_saved.status_code)

            alpha_annotations_path = (
                workspace
                / ".echobot"
                / "live2d"
                / "duo"
                / "alpha"
                / "echobot.live2d.json"
            )
            beta_annotations_path = (
                workspace
                / ".echobot"
                / "live2d"
                / "duo"
                / "beta"
                / "echobot.live2d.json"
            )
            alpha_annotations = json.loads(alpha_annotations_path.read_text(encoding="utf-8"))
            beta_annotations = json.loads(beta_annotations_path.read_text(encoding="utf-8"))

            self.assertEqual(
                "alpha custom note",
                alpha_annotations["expressions"]["smile.exp3.json"],
            )
            self.assertEqual(
                "beta default note",
                beta_annotations["expressions"]["smile.exp3.json"],
            )
            self.assertNotIn("hk_smile", alpha_annotations["hotkeys"])
            self.assertEqual(
                ["alt", "digit9"],
                beta_annotations["hotkeys"]["hk_smile"]["shortcut_tokens"],
            )

            refreshed_models = {
                item["model_name"]: item
                for item in refreshed.json()["live2d"]["models"]
                if item["source"] == "workspace"
            }
            self.assertEqual(
                "alpha custom note",
                next(
                    item["note"]
                    for item in refreshed_models["alpha"]["expressions"]
                    if item["file"] == "smile.exp3.json"
                ),
            )
            self.assertEqual(
                "beta default note",
                next(
                    item["note"]
                    for item in refreshed_models["beta"]["expressions"]
                    if item["file"] == "smile.exp3.json"
                ),
            )
            self.assertEqual(
                ["alt", "digit9"],
                next(
                    item["shortcut_tokens"]
                    for item in refreshed_models["beta"]["hotkeys"]
                    if item["hotkey_key"] == "hk_smile"
                ),
            )

    def test_web_console_prefers_configured_live2d_model_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_live2d_model(workspace)
            write_test_hiyori_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with patch.dict(
                os.environ,
                {"ECHOBOT_WEB_LIVE2D_MODEL": "hiyori_pro_en"},
                clear=False,
            ):
                with TestClient(app) as client:
                    config = client.get("/api/web/config")

            self.assertEqual(200, config.status_code)
            payload = config.json()
            self.assertEqual("hiyori_pro_t11", payload["live2d"]["model_name"])
            self.assertEqual("hiyori_pro_en", payload["live2d"]["directory_name"])
            self.assertEqual(
                "workspace:hiyori_pro_en/runtime/hiyori_pro_t11.model3.json",
                payload["live2d"]["selection_key"],
            )
            self.assertIn(
                "/api/web/live2d/workspace/hiyori_pro_en/runtime/hiyori_pro_t11.model3.json",
                payload["live2d"]["model_url"],
            )

    def test_web_console_falls_back_when_configured_live2d_model_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            write_test_live2d_model(workspace)
            write_test_hiyori_live2d_model(workspace)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with patch.dict(
                os.environ,
                {"ECHOBOT_WEB_LIVE2D_MODEL": "missing-model"},
                clear=False,
            ):
                with TestClient(app) as client:
                    config = client.get("/api/web/config")

            self.assertEqual(200, config.status_code)
            payload = config.json()
            self.assertIn("%E5%85%94%E5%85%94", payload["live2d"]["model_url"])

    def test_web_console_uses_builtin_live2d_when_workspace_has_none(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                config = client.get("/api/web/config")

            self.assertEqual(200, config.status_code)
            payload = config.json()
            self.assertTrue(payload["live2d"]["available"])
            self.assertIn("/api/web/live2d/builtin/", payload["live2d"]["model_url"])

    def test_web_console_can_select_builtin_live2d_by_source_prefixed_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with patch.dict(
                os.environ,
                {"ECHOBOT_WEB_LIVE2D_MODEL": "builtin:mao_pro_en"},
                clear=False,
            ):
                with TestClient(app) as client:
                    config = client.get("/api/web/config")
                    payload = config.json()
                    model_response = client.get(payload["live2d"]["model_url"])

            self.assertEqual(200, config.status_code)
            self.assertEqual("mao_pro_en", payload["live2d"]["directory_name"])
            self.assertEqual(
                "builtin:mao_pro_en/runtime/mao_pro.model3.json",
                payload["live2d"]["selection_key"],
            )
            self.assertEqual(["ParamA"], payload["live2d"]["lip_sync_parameter_ids"])
            self.assertIn("/api/web/live2d/builtin/mao_pro_en/", payload["live2d"]["model_url"])
            self.assertEqual(200, model_response.status_code)

    def test_web_tts_routes_work_with_injected_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                voices = client.get("/api/web/tts/voices?provider=edge")
                kokoro_voices = client.get("/api/web/tts/voices?provider=kokoro")
                speech = client.post(
                    "/api/web/tts",
                    json={
                        "text": "你好",
                        "provider": "edge",
                        "voice": "zh-CN-XiaoxiaoNeural",
                    },
                )
                kokoro_speech = client.post(
                    "/api/web/tts",
                    json={
                        "text": "你好",
                        "provider": "kokoro",
                        "voice": "zf_001",
                    },
                )

            self.assertEqual(200, voices.status_code)
            self.assertEqual("edge", voices.json()["provider"])
            self.assertEqual("zh-CN-XiaoxiaoNeural", voices.json()["voices"][0]["short_name"])
            self.assertEqual(200, kokoro_voices.status_code)
            self.assertEqual("kokoro", kokoro_voices.json()["provider"])
            self.assertEqual("zf_001", kokoro_voices.json()["voices"][0]["short_name"])

            self.assertEqual(200, speech.status_code)
            self.assertEqual("audio/mpeg", speech.headers["content-type"])
            self.assertEqual("edge", speech.headers["x-tts-provider"])
            self.assertEqual("zh-CN-XiaoxiaoNeural", speech.headers["x-tts-voice"])
            self.assertIn(b"fake-audio:zh-CN-XiaoxiaoNeural:\xe4\xbd\xa0\xe5\xa5\xbd", speech.content)
            self.assertEqual(200, kokoro_speech.status_code)
            self.assertEqual("audio/wav", kokoro_speech.headers["content-type"])
            self.assertEqual("kokoro", kokoro_speech.headers["x-tts-provider"])
            self.assertEqual("zf_001", kokoro_speech.headers["x-tts-voice"])
            self.assertIn(b"fake-kokoro:zf_001:\xe4\xbd\xa0\xe5\xa5\xbd", kokoro_speech.content)

    def test_web_tts_endpoint_ignores_emojis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                speech = client.post(
                    "/api/web/tts",
                    json={
                        "text": "Hello 😊 world",
                        "provider": "edge",
                        "voice": "zh-CN-XiaoxiaoNeural",
                    },
                )
                emoji_only_speech = client.post(
                    "/api/web/tts",
                    json={
                        "text": "😊🎉",
                        "provider": "edge",
                        "voice": "zh-CN-XiaoxiaoNeural",
                    },
                )

            self.assertEqual(200, speech.status_code)
            self.assertEqual(
                b"fake-audio:zh-CN-XiaoxiaoNeural:Hello world",
                speech.content,
            )
            self.assertEqual(400, emoji_only_speech.status_code)
            self.assertEqual(
                "TTS text must not be empty",
                emoji_only_speech.json()["detail"],
            )

    def test_web_asr_routes_work_with_injected_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            app = create_app(
                runtime_options=RuntimeOptions(
                    workspace=workspace,
                    no_tools=True,
                    no_skills=True,
                    no_memory=True,
                    no_heartbeat=True,
                ),
                channel_config_path=workspace / ".echobot" / "channels.json",
                context_builder=build_test_context,
                tts_service_builder=build_test_tts_service,
                asr_service_builder=build_test_asr_service,
            )

            with TestClient(app) as client:
                status = client.get("/api/web/asr/status")
                transcript = client.post(
                    "/api/web/asr",
                    content=b"fake-wav",
                    headers={"content-type": "audio/wav"},
                )
                with client.websocket_connect("/api/web/asr/ws") as websocket:
                    ready_event = websocket.receive_json()
                    websocket.send_bytes(b"hello from websocket")
                    transcript_event = websocket.receive_json()
                    websocket.send_text("flush")
                    flush_event = websocket.receive_json()

            self.assertEqual(200, status.status_code)
            self.assertTrue(status.json()["available"])
            self.assertEqual("ready", status.json()["state"])

            self.assertEqual(200, transcript.status_code)
            self.assertEqual("zh", transcript.json()["language"])
            self.assertEqual("voice-8", transcript.json()["text"])

            self.assertEqual("ready", ready_event["type"])
            self.assertEqual(16000, ready_event["sample_rate"])
            self.assertEqual("transcript", transcript_event["type"])
            self.assertEqual("hello from websocket", transcript_event["text"])
            self.assertEqual("flush_complete", flush_event["type"])

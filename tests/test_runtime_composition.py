from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from echobot.app.services.runtime_composition import (
    RuntimeComposition,
    build_runtime_composition,
)


class _SpeechService:
    def __init__(self, name: str) -> None:
        self.name = name


def _context(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        workspace=tmp_path,
        storage_root=tmp_path / ".echobot",
        session_store=object(),
        agent_session_store=object(),
        coordinator=object(),
        role_registry=object(),
    )


def test_runtime_composition_builds_shared_service_graph(tmp_path: Path) -> None:
    context = _context(tmp_path)
    tts = _SpeechService("tts")
    asr = _SpeechService("asr")

    composition = build_runtime_composition(
        context=context,
        storage_root=tmp_path / ".echobot",
        tts_service=tts,
        asr_service=asr,
    )

    assert isinstance(composition, RuntimeComposition)
    assert composition.tts_service is tts
    assert composition.asr_service is asr
    assert composition.session_service is not None
    assert composition.chat_service is not None
    assert composition.role_service is not None
    assert composition.character_profile_settings_service is not None
    assert composition.model_profile_service is not None
    assert composition.llm_model_service is not None
    assert composition.voice_model_service is not None
    assert composition.live2d_model_service is not None
    assert composition.web_console_service is not None
    assert composition.runtime_profile_applier is not None
    assert composition.channel_service is None


def test_runtime_composition_app_and_user_inputs_have_parity(tmp_path: Path) -> None:
    app_context = _context(tmp_path / "app")
    user_context = _context(tmp_path / "user")

    app = build_runtime_composition(
        context=app_context,
        storage_root=app_context.storage_root,
        tts_service=_SpeechService("app-tts"),
        asr_service=_SpeechService("app-asr"),
        channel_config_path=tmp_path / "channels.json",
        get_channel_status=lambda: {},
        reload_channels=lambda _config: None,
    )
    user = build_runtime_composition(
        context=user_context,
        storage_root=user_context.storage_root,
        tts_service=_SpeechService("user-tts"),
        asr_service=_SpeechService("user-asr"),
    )

    service_names = (
        "session_service",
        "chat_service",
        "role_service",
        "character_profile_settings_service",
        "model_profile_service",
        "llm_model_service",
        "voice_model_service",
        "live2d_model_service",
        "web_console_service",
        "runtime_profile_applier",
    )
    for name in service_names:
        assert type(getattr(app, name)) is type(getattr(user, name))
    assert app.channel_service is not None
    assert user.channel_service is None

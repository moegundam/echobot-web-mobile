from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "echobot" / "app" / "web"
MESSENGER_ROOT = WEB_ROOT / "features" / "messenger"


def read_module(name: str) -> str:
    return (MESSENGER_ROOT / name).read_text(encoding="utf-8")


def test_messenger_entrypoint_is_a_composition_root() -> None:
    entrypoint = (WEB_ROOT / "messenger-app.js").read_text(encoding="utf-8")

    assert len(entrypoint.splitlines()) < 420
    for module_name in (
        "session-runtime.js",
        "message-stream.js",
        "attachments.js",
        "microphone.js",
    ):
        assert f'./features/messenger/{module_name}' in entrypoint


def test_messenger_modules_have_single_responsibility_boundaries() -> None:
    session_runtime = read_module("session-runtime.js")
    message_stream = read_module("message-stream.js")
    attachments = read_module("attachments.js")
    microphone = read_module("microphone.js")

    assert "export function createMessengerSessionController" in session_runtime
    assert "loadSessions" in session_runtime
    assert "loadMessengerRuntimeContext" in session_runtime
    assert "export function createMessengerMessageController" in message_stream
    assert "route_mode: activeRouteMode(sessionName)" in message_stream
    assert "getResponseLanguagePayload" in message_stream
    assert "onChunk: async (delta)" in message_stream
    assert "onDone: async (event)" in message_stream
    assert "requestChatStream" not in session_runtime
    assert "export function createMessengerAttachmentController" in attachments
    assert "uploadMessengerAttachment" in attachments
    assert "uploadChatImage" in attachments
    assert "uploadChatFile" in attachments
    assert "export function createMessengerMicrophoneController" in microphone
    assert "createSpeechRecognition" in microphone
    assert "recognition.onresult" in microphone
    assert "recognition.onerror" in microphone
    assert "recognition.stop()" in microphone
    assert "visibilitychange" in microphone
    assert "pagehide" in microphone


def test_messenger_entrypoint_keeps_behavioral_adapters_explicit() -> None:
    entrypoint = (WEB_ROOT / "messenger-app.js").read_text(encoding="utf-8")

    assert 'const FALLBACK_ROUTE_MODE = "chat_only";' in entrypoint
    assert "function selectedSessionName(" in entrypoint
    assert "function isMessagesNearBottom(" in entrypoint
    assert "function speechRecognitionErrorStatusKey(" in entrypoint
    assert 'source: "messenger"' in entrypoint

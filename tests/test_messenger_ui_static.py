from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "echobot" / "app" / "web"


def read_web_file(name: str) -> str:
    return (WEB_ROOT / name).read_text(encoding="utf-8")


def test_messenger_primary_composer_has_a_localized_label() -> None:
    html = read_web_file("messenger.html")

    assert re.search(
        r'<label[^>]+for="messenger-input"[^>]*data-i18n-key="messenger\.inputPlaceholder"',
        html,
    )
    assert 'id="messenger-input"' in html


def test_messenger_status_is_the_single_polite_status_region() -> None:
    html = read_web_file("messenger.html")

    assert re.search(
        r'<p id="messenger-status"[^>]+role="status"[^>]+aria-live="polite"[^>]+aria-atomic="true"',
        html,
    )
    assert '<section id="messenger-messages" class="messenger-messages" aria-live=' not in html
    assert 'id="messenger-empty-state"' in html


def test_messenger_streaming_updates_preserve_near_bottom_only() -> None:
    source = read_web_file("messenger-app.js")

    assert "function isMessagesNearBottom(" in source
    assert "function scrollMessagesIfNearBottom(" in source
    assert "scrollMessagesIfNearBottom(() =>" in source
    assert "scrollMessagesToBottom(element);" in source


def test_messenger_microphone_errors_have_distinct_recovery_statuses() -> None:
    source = read_web_file("messenger-app.js")

    assert "function speechRecognitionErrorStatusKey(" in source
    for key in (
        "console.microphonePermissionDenied",
        "console.microphoneNotFound",
        "console.noValidSpeech",
        "console.asrFailed",
        "console.microphoneCaptureUnsupported",
        "console.microphoneStartFailed",
    ):
        assert key in source


def test_messenger_file_input_is_not_a_keyboard_focus_stop() -> None:
    html = read_web_file("messenger.html")

    assert re.search(
        r'<input id="messenger-file-input"[^>]+tabindex="-1"[^>]+aria-hidden="true"',
        html,
    )
    assert 'id="messenger-file-button"' in html
    assert 'aria-controls="messenger-file-input"' in html


def test_messenger_resolves_an_existing_session_before_context_fetch() -> None:
    source = (
        WEB_ROOT / "features" / "messenger" / "session-runtime.js"
    ).read_text(encoding="utf-8")
    init_block = source.split("function init() {", 1)[1].split(
        "async function loadSessions()",
        1,
    )[0]

    assert "resolveAvailableSessionName" in source
    assert "loadMessengerRuntimeContext(initialSessionName)" not in init_block
    assert "void loadSessions();" in init_block
    guard_index = source.index("if (!knownSessionNames.has(requestedSessionName))")
    fetch_index = source.index("fetchSessionRuntimeContext(requestedSessionName)")
    assert guard_index < fetch_index

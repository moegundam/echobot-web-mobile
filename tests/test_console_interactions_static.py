from __future__ import annotations

from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "echobot" / "app" / "web"


def read_web_file(relative_path: str) -> str:
    return (WEB_ROOT / relative_path).read_text(encoding="utf-8")


def function_block(source: str, function_name: str, next_function_name: str) -> str:
    start = source.index(f"function {function_name}")
    end = source.index(f"function {next_function_name}", start)
    return source[start:end]


def test_streaming_message_updates_only_follow_an_existing_bottom_position() -> None:
    source = read_web_file("modules/messages.js")
    update_block = function_block(source, "updateMessage", "clearMessages")

    assert "const shouldFollowBottom = shouldFollowMessagesBottom();" in update_block
    assert update_block.index("const shouldFollowBottom") < update_block.index(
        "renderMessageBody",
    )
    assert (
        "scheduleMessagesScrollToBottom({ onlyIfFollowing: shouldFollowBottom });"
        in update_block
    )
    assert "const MESSAGE_BOTTOM_THRESHOLD_PX" in source
    assert 'pendingScrollMode === "follow"' in source
    assert 'Symbol.for("echobot.messages.followBottom")' in source
    assert "DOM.messages.addEventListener(\"scroll\", updateMessagesFollowState);" in source
    assert "setMessagesFollowBottom(isMessagesNearBottom());" in source
    assert "getMessagesFollowBottom()" in source


def test_new_messages_keep_the_existing_explicit_scroll_contract() -> None:
    source = read_web_file("modules/messages.js")
    add_block = function_block(source, "addMessage", "addSystemMessage")

    assert "scheduleMessagesScrollToBottom({ force: true });" in add_block
    assert "onlyIfFollowing" not in add_block
    assert "const forceScroll = options.force === true;" in source
    assert 'const requestedMode = forceScroll ? "force" : "follow";' in source


def test_live2d_tabs_support_roving_keyboard_activation() -> None:
    sidebars = read_web_file("features/layout/sidebars.js")
    wiring = read_web_file("bootstrap/wire-events.js")

    assert "function handleLive2DDrawerTabKeyDown(event)" in sidebars
    assert 'event.key === "ArrowRight"' in sidebars
    assert 'event.key === "ArrowLeft"' in sidebars
    assert 'event.key === "Home"' in sidebars
    assert 'event.key === "End"' in sidebars
    assert "setLive2DDrawerTab(nextTabKey, { focusTab: true });" in sidebars
    assert "button?.focus({ preventScroll: true });" in sidebars
    assert (
        'bindOptionalEventHandler(tab, "keydown", '
        "layout.handleLive2DDrawerTabKeyDown);"
        in wiring
    )


def test_console_drawers_share_escape_focus_trap_and_focus_restore() -> None:
    sidebars = read_web_file("features/layout/sidebars.js")
    wiring = read_web_file("bootstrap/wire-events.js")

    assert "function handleDrawerKeyDown(event)" in sidebars
    assert 'event.key === "Escape"' in sidebars
    assert 'event.key === "Tab"' in sidebars
    assert "trapDrawerFocus(event, activeDrawer.element);" in sidebars
    assert "drawerPreviousFocus.set(drawerKey, document.activeElement);" in sidebars
    assert "scheduleDrawerFocus(drawer, preferredFocus);" in sidebars
    assert "window.setTimeout(() =>" in sidebars
    assert "window.queueMicrotask" not in sidebars
    assert "restoreDrawerFocus(drawerKey, fallbackToggle);" in sidebars
    assert "element.focus({ preventScroll: true });" in sidebars
    assert 'drawer.setAttribute("role", "dialog");' in sidebars
    assert 'drawer.toggleAttribute("inert", !isOpen);' in sidebars
    assert (
        'window.addEventListener("keydown", layout.handleDrawerKeyDown);'
        in wiring
    )


def test_console_announces_only_completed_assistant_replies() -> None:
    html = read_web_file("index.html")
    dom_js = read_web_file("core/dom.js")
    messages_js = read_web_file("modules/messages.js")
    job_runner_js = read_web_file("features/chat/job-runner.js")
    sessions_js = read_web_file("features/sessions.js")

    assert (
        '<p id="assistant-announcement" class="sr-only" '
        'role="status" aria-live="polite" aria-atomic="true"></p>'
    ) in html
    assert "assistantAnnouncement" in dom_js
    assert "export function announceAssistantMessage(content)" in messages_js
    assert "messageContentToText(content" in messages_js

    stream_handler = job_runner_js.split("onChunk(delta) {", 1)[1].split("},", 1)[0]
    assert "announceAssistantMessage" not in stream_handler
    assert "announceAssistantMessage(finalContent || finalText);" in job_runner_js
    assert "announceAssistantMessage(spokenText);" in sessions_js


def test_public_guide_and_role_aware_navigation_are_wired() -> None:
    routes = read_web_file("../web_pages.py")
    auth = read_web_file("../auth.py")
    guide_html = read_web_file("guide.html")
    guide_js = read_web_file("guide-app.js")
    access_js = read_web_file("features/access.js")
    stage_html = read_web_file("stage.html")
    messenger_html = read_web_file("messenger.html")

    assert 'WebPageRoute("/guide", "guide.html", "guide")' in routes
    assert 'path == "/guide"' in auth
    assert 'href="/admin" data-admin-only hidden' in guide_html
    assert 'href="/console" data-operator-only hidden' in guide_html
    assert "initShellAccessContext" in guide_js
    assert "section.audience" in guide_js
    assert "appendInlineNavigation" in guide_js
    assert 'document.createElement("a")' in guide_js
    assert "[data-operator-only]" in access_js
    assert "can_access_console" in access_js
    assert 'href="/admin" data-admin-only hidden' in stage_html
    assert 'href="/admin" data-admin-only hidden' in messenger_html


def test_model_connection_status_and_i18n_contract_are_explicit() -> None:
    app_js = read_web_file("app.js")
    models_html = read_web_file("models.html")
    models_js = read_web_file("models-app.js")
    catalogs = "\n".join(
        read_web_file(path)
        for path in (
            "i18n/catalog-en.js",
            "i18n/catalog-zh-Hant.js",
            "i18n/catalog-zh-Hans.js",
        )
    )

    assert 'id="model-profile-smoke"' in models_html
    assert '"/smoke"' in models_js
    assert "smokeSelectedProfile" in models_js
    assert 'setStatusKey("models.settingsLoaded")' in models_js
    assert 'setStatusKey("models.ready")' not in models_js
    assert 'i18n.t("console.roleModelProfileMissing"' in app_js
    assert 'i18n.t("console.modelProfileMissing"' not in app_js
    for key in (
        "models.settingsLoaded",
        "models.smokeTest",
        "models.smokeTesting",
        "models.smokeReady",
        "models.smokeFailed",
        "models.smokeSaveFirst",
    ):
        assert catalogs.count(f'"{key}"') == 3

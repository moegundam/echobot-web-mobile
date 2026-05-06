from __future__ import annotations

import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "echobot" / "app" / "web"


class WebStaticAssetTests(unittest.TestCase):
    def test_display_mode_uses_layout_mode_contract(self) -> None:
        display_mode_js = (WEB_ROOT / "shell-display-mode.js").read_text(encoding="utf-8")
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        shell_pages_css = (WEB_ROOT / "styles" / "shell-pages.css").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn("dataset.layoutMode", display_mode_js)
        self.assertIn("dataset.requestedDisplayMode", display_mode_js)
        self.assertIn('"displayMode.tablet"', i18n_js)
        self.assertNotIn('{ code: "portrait"', display_mode_js)
        self.assertNotIn('{ code: "landscape"', display_mode_js)
        self.assertNotIn('data-effective-display-mode="portrait"', responsive_css)
        self.assertNotIn('data-effective-display-mode="landscape"', responsive_css)
        self.assertNotIn('data-effective-display-mode="portrait"', shell_pages_css)
        self.assertNotIn('data-effective-display-mode="landscape"', shell_pages_css)

    def test_html_translatable_attributes_have_i18n_keys(self) -> None:
        checked_attributes = {
            "aria-label": "data-i18n-aria-label-key",
            "placeholder": "data-i18n-placeholder-key",
            "title": "data-i18n-title-key",
        }

        failures: list[str] = []
        for html_path in sorted(WEB_ROOT.glob("*.html")):
            html = html_path.read_text(encoding="utf-8")
            for match in re.finditer(r"<([A-Za-z][\w:-]*)([^<>]*)>", html):
                tag_name = match.group(1).lower()
                if tag_name in {"html", "meta", "link", "script"}:
                    continue
                attrs = match.group(2)
                for attr_name, i18n_attr_name in checked_attributes.items():
                    if re.search(rf"\b{re.escape(attr_name)}=\"[^\"]+\"", attrs):
                        if not re.search(rf"\b{re.escape(i18n_attr_name)}=\"[^\"]+\"", attrs):
                            failures.append(
                                f"{html_path.relative_to(WEB_ROOT)} <{tag_name}> missing {i18n_attr_name} for {attr_name}",
                            )

        self.assertEqual([], failures)

    def test_console_exposes_role_model_profile_and_control_groups(self) -> None:
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        sessions_js = (WEB_ROOT / "features" / "sessions.js").read_text(encoding="utf-8")
        session_sidebar_js = (WEB_ROOT / "features" / "sessions" / "sidebar.js").read_text(encoding="utf-8")
        route_mode_js = (WEB_ROOT / "features" / "sessions" / "route-mode.js").read_text(encoding="utf-8")
        chat_runner_js = (WEB_ROOT / "features" / "chat" / "job-runner.js").read_text(encoding="utf-8")
        roles_js = (WEB_ROOT / "features" / "roles.js").read_text(encoding="utf-8")
        panels_css = (WEB_ROOT / "styles" / "panels.css").read_text(encoding="utf-8")
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('id="session-settings-summary"', html)
        self.assertIn('id="session-settings-current"', html)
        self.assertIn('id="session-settings-source"', html)
        self.assertIn('id="session-settings-role"', html)
        self.assertIn('id="session-settings-model"', html)
        self.assertIn('id="session-settings-route"', html)
        self.assertIn('id="session-settings-updated"', html)
        self.assertIn('id="session-settings-stage-link"', html)
        self.assertIn('id="session-settings-messenger-link"', html)
        self.assertIn('class="console-admin-handoff"', html)
        self.assertIn('href="/admin/voice-models"', html)
        self.assertIn('href="/admin/live2d"', html)
        self.assertIn('id="role-model-profile-card"', html)
        self.assertIn('id="role-model-profile-link"', html)
        self.assertIn('id="role-model-profile-detail"', html)
        self.assertIn('href="/admin/sessions"', html)
        self.assertIn('href="/admin/characters"', html)
        self.assertNotIn('id="session-create-button"', html)
        self.assertNotIn('id="role-editor"', html)
        self.assertNotIn('id="role-new-button"', html)
        self.assertNotIn('id="role-edit-button"', html)
        self.assertNotIn('id="role-delete-button"', html)
        self.assertNotIn('id="role-save-button"', html)
        self.assertNotIn('id="role-cancel-button"', html)
        self.assertIn('id="model-profile-select"', html)
        self.assertIn('id="model-profile-link"', html)
        self.assertIn('id="console-advanced-overrides-panel"', html)
        self.assertIn('data-i18n-key="console.advancedOverrides"', html)
        self.assertIn('data-i18n-key="console.advancedOverridesHelp"', html)
        self.assertIn('data-i18n-key="console.groupModelRouting"', html)
        self.assertIn('data-i18n-key="console.groupVoice"', html)
        self.assertIn('data-i18n-key="console.groupLive2dStage"', html)
        self.assertIn('data-i18n-key="console.groupRuntimeJobs"', html)
        self.assertIn("syncModelProfileFromServer", app_js)
        self.assertIn("activateConsoleModelProfile", app_js)
        self.assertIn("/api/model-profiles/${encodeURIComponent(nextProfileId)}/activate", app_js)
        self.assertIn("notifyModelProfileChanged", app_js)
        self.assertIn("getUiLanguage: () => i18n.language", app_js)
        self.assertIn('"/api/channels/stage-targets"', sessions_js)
        self.assertIn("renderSessionSettings", sessions_js)
        self.assertIn("sessionModelProfileLabel", sessions_js)
        self.assertIn("sessionSourceLabel", sessions_js)
        self.assertIn('value === "agent"', route_mode_js)
        self.assertIn('return "force_agent"', route_mode_js)
        self.assertNotIn("handleCreateSession", sessions_js)
        self.assertNotIn('action === "rename"', sessions_js)
        self.assertNotIn('action === "delete"', sessions_js)
        self.assertNotIn('requestJson("/api/roles", {\n                    method: "POST"', roles_js)
        self.assertNotIn('`/api/roles/${encodeURIComponent(roleState.currentRoleName)}`', roles_js)
        self.assertNotIn('`/api/roles/${encodeURIComponent(roleCard.name)}`', roles_js)
        self.assertNotIn('t("console.rename")', session_sidebar_js)
        self.assertNotIn('t("console.delete")', session_sidebar_js)
        self.assertIn(".session-settings-summary-block", panels_css)
        self.assertIn(".console-admin-handoff", panels_css)
        self.assertIn(".session-settings-grid", panels_css)
        self.assertIn(".session-settings-grid", responsive_css)
        self.assertIn("@media (max-width: 899px)", responsive_css)
        self.assertIn('html[data-layout-mode="tablet"][data-viewport-orientation="landscape"] .page-shell', responsive_css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(320px, min(44vw, 420px));", responsive_css)
        self.assertIn("html[data-layout-mode=\"tablet\"] .page-resizer", responsive_css)
        self.assertIn("max-height: min(46vh, 500px)", panels_css)
        self.assertIn("response_language: getUiLanguage()", chat_runner_js)
        self.assertIn("renderRoleModelProfileCard", roles_js)
        self.assertIn('window.location.pathname === "/console"', app_js)
        self.assertIn("document.body.dataset.shellMode = shellMode", app_js)

        for key in (
            "console.sessionSettings",
            "console.sessionSettingsHelp",
            "console.adminHandoff",
            "console.adminHandoffHelp",
            "console.advancedOverrides",
            "console.advancedOverridesHelp",
            "console.sessionSettingCurrent",
            "console.sessionSettingSource",
            "console.sessionSettingRole",
            "console.sessionSettingModel",
            "console.sessionSettingRoute",
            "console.sessionSettingUpdated",
            "console.sessionSourceManual",
            "console.openStage",
            "console.openMessenger",
            "admin.sessions",
            "console.modelProfileManage",
            "console.modelProfileSwitching",
            "console.modelProfileSwitched",
            "console.modelProfileSwitchFailed",
            "console.roleModelProfile",
            "console.roleModelProfileBound",
            "console.roleModelProfileUnbound",
            "console.roleSwitchedWithProfile",
            "console.groupModelRouting",
            "console.groupVoice",
            "console.groupLive2dStage",
            "console.groupRuntimeJobs",
        ):
            self.assertIn(f'"{key}"', i18n_js)

    def test_admin_sessions_page_owns_session_maintenance(self) -> None:
        app_routes = (WEB_ROOT.parents[0] / "web_pages.py").read_text(encoding="utf-8")
        admin_html = (WEB_ROOT / "admin.html").read_text(encoding="utf-8")
        sessions_html = (WEB_ROOT / "sessions.html").read_text(encoding="utf-8")
        sessions_js = (WEB_ROOT / "sessions-app.js").read_text(encoding="utf-8")
        structure_js = (WEB_ROOT / "structure-app.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('WebPageRoute("/admin/sessions"', app_routes)
        self.assertIn('href="/admin/sessions"', admin_html)
        self.assertIn('data-i18n-key="admin.sessions"', admin_html)
        self.assertNotIn("Read-only admin index", admin_html)
        self.assertIn('id="sessions-list"', sessions_html)
        self.assertIn('id="sessions-create-form"', sessions_html)
        self.assertIn('id="sessions-create"', sessions_html)
        self.assertIn('id="sessions-create-name"', sessions_html)
        self.assertIn('id="sessions-create-character"', sessions_html)
        self.assertIn('id="sessions-create-route-mode"', sessions_html)
        self.assertIn('value="force_agent"', sessions_html)
        self.assertNotIn('value="agent"', sessions_html)
        self.assertIn('id="sessions-create-channel-type"', sessions_html)
        self.assertIn('id="sessions-create-channel-integration"', sessions_html)
        self.assertIn('id="sessions-edit-form"', sessions_html)
        self.assertIn('id="sessions-edit-character"', sessions_html)
        self.assertIn('id="sessions-edit-route-mode"', sessions_html)
        self.assertIn('id="sessions-edit-channel-type"', sessions_html)
        self.assertIn('id="sessions-edit-channel-integration"', sessions_html)
        self.assertIn('id="sessions-edit-save"', sessions_html)
        self.assertIn('id="sessions-refresh"', sessions_html)
        self.assertIn('"/api/sessions"', sessions_js)
        self.assertIn('"/api/character-profiles"', sessions_js)
        self.assertIn('"/api/channel-integrations"', sessions_js)
        self.assertIn('"/api/sessions/current"', sessions_js)
        self.assertIn('/role`', sessions_js)
        self.assertIn('/route-mode`', sessions_js)
        self.assertIn('/channel-binding`', sessions_js)
        self.assertIn("editSession", sessions_js)
        self.assertIn("saveSessionBinding", sessions_js)
        self.assertIn("renameSession", sessions_js)
        self.assertIn("deleteSession", sessions_js)
        self.assertIn("syncChannelTypeFromIntegration", sessions_js)
        self.assertIn("/admin/sessions", structure_js)

        for key in (
            "sessions.pageTitle",
            "sessions.heading",
            "sessions.description",
            "sessions.management",
            "sessions.name",
            "sessions.namePlaceholder",
            "sessions.nameRequired",
            "sessions.character",
            "sessions.useDefaultCharacter",
            "sessions.routeMode",
            "sessions.channelType",
            "sessions.channelIntegration",
            "sessions.noChannelBinding",
            "sessions.noChannelIntegration",
            "sessions.create",
            "sessions.refresh",
            "sessions.useInConsole",
            "sessions.edit",
            "sessions.saveBinding",
            "sessions.bindingSaved",
            "sessions.rename",
            "sessions.delete",
            "sessions.deleteConfirm",
            "sessions.roleMeta",
            "sessions.routeMeta",
            "sessions.channelMeta",
        ):
            self.assertGreaterEqual(i18n_js.count(f'"{key}"'), 3)

    def test_messenger_stage_stream_contract_is_explicit(self) -> None:
        messenger_html = (WEB_ROOT / "messenger.html").read_text(encoding="utf-8")
        stage_html = (WEB_ROOT / "stage.html").read_text(encoding="utf-8")
        messenger_js = (WEB_ROOT / "messenger-app.js").read_text(encoding="utf-8")
        stage_js = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")
        runtime_context_js = (WEB_ROOT / "session-runtime-context.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('id="messenger-session-select"', messenger_html)
        self.assertIn('id="messenger-runtime-context"', messenger_html)
        self.assertIn('id="messenger-record"', messenger_html)
        self.assertIn('id="messenger-url"', messenger_html)
        self.assertIn('id="messenger-file-input"', messenger_html)
        self.assertIn('id="messenger-attachments"', messenger_html)
        self.assertIn('id="stage-session-select"', stage_html)
        self.assertIn('data-i18n-key="stage.sessionTarget">Session</span>', stage_html)
        self.assertIn('id="stage-role-label"', stage_html)
        self.assertIn('id="stage-model-profile-label"', stage_html)
        self.assertIn('id="stage-voice-profile-label"', stage_html)
        self.assertIn('id="stage-live2d-profile-label"', stage_html)
        self.assertIn('id="stage-channel-label"', stage_html)
        self.assertIn('"/api/sessions"', messenger_js)
        self.assertIn('"/api/channels/stage-targets"', messenger_js)
        self.assertIn('"/api/channels/stage-targets"', stage_js)
        self.assertIn("/runtime-context", runtime_context_js)
        self.assertIn("fetchSessionRuntimeContext", messenger_js)
        self.assertIn("fetchSessionRuntimeContext", stage_js)
        self.assertIn("runtimeContextSummaryItems", messenger_js)
        self.assertIn("runtimeContextValue", stage_js)
        self.assertIn("STAGE_CONTEXT_REFRESH_INTERVAL_MS", stage_js)
        self.assertIn("stageContextLive2DConfig", stage_js)
        self.assertIn("reloadLive2DFromContext", stage_js)
        self.assertIn("canvasHost.dataset.live2dSelectionKey", stage_js)
        self.assertNotIn("normalizeLive2DConfig(config && config.live2d)", stage_js)
        self.assertIn("loadSessions", messenger_js)
        self.assertIn("uploadSelectedFiles", messenger_js)
        self.assertIn("uploadMessengerAttachment", messenger_js)
        self.assertIn("pendingAttachments", messenger_js)
        self.assertIn("promptWithUrl", messenger_js)
        self.assertIn("createSpeechRecognition", messenger_js)
        self.assertIn("loadStageTargets", stage_js)
        self.assertNotIn("/api/stage/context?session_name=", stage_js)
        self.assertIn("loadStageContext", stage_js)
        self.assertIn("renderStageContext", stage_js)
        self.assertIn('route_mode: DEFAULT_ROUTE_MODE', messenger_js)
        self.assertIn("response_language: i18n.language", messenger_js)
        self.assertIn('const DEFAULT_ROUTE_MODE = "chat_only";', messenger_js)
        self.assertIn("extractStageDirectives", messenger_js)
        self.assertIn("stageDirectivePattern", messenger_js)
        self.assertIn('await publishStageEvent("subtitle", sessionName, ""', messenger_js)
        self.assertIn('await publishStageEvent("assistant_delta", sessionName, delta', messenger_js)
        self.assertIn('await publishStageEvent("assistant_final", sessionName, stageMessage.text', messenger_js)
        self.assertIn("expression: stageMessage.expression", messenger_js)
        self.assertIn("motion: stageMessage.motion", messenger_js)
        self.assertIn('source: "messenger"', messenger_js)
        self.assertIn('"/api/stage/events"', messenger_js)

        self.assertIn("new EventSource(url)", stage_js)
        self.assertIn("stageEventSource.close()", stage_js)
        self.assertIn('source.addEventListener("assistant_delta"', stage_js)
        self.assertIn('source.addEventListener("assistant_final"', stage_js)
        self.assertIn('source.addEventListener("character_state"', stage_js)
        self.assertIn("applyStageVisualState(payload)", stage_js)
        self.assertIn("applyStageExpression", stage_js)
        self.assertIn("playStageMotion", stage_js)
        self.assertIn("subtitleElement.textContent", stage_js)
        self.assertNotIn("subtitleElement.innerHTML", stage_js)
        self.assertGreaterEqual(i18n_js.count('"stage.sessionTarget": "Session"'), 3)
        self.assertGreaterEqual(i18n_js.count('"messenger.sessionTarget": "Session"'), 3)
        self.assertNotIn('"stage.sessionTarget": "Target"', i18n_js)
        self.assertNotIn('"stage.sessionTarget": "通訊目標"', i18n_js)
        self.assertNotIn('"stage.sessionTarget": "通讯目标"', i18n_js)
        self.assertNotIn('"messenger.sessionTarget": "Target"', i18n_js)
        self.assertNotIn('"messenger.sessionTarget": "通訊目標"', i18n_js)
        self.assertNotIn('"messenger.sessionTarget": "通讯目标"', i18n_js)

        delta_handler = re.search(
            r'source\.addEventListener\("assistant_delta".*?\}\);',
            stage_js,
            flags=re.S,
        )
        final_handler = re.search(
            r'source\.addEventListener\("assistant_final".*?'
            r'await playTts\(payload\.text\);.*?\n    \}\);',
            stage_js,
            flags=re.S,
        )
        self.assertIsNotNone(delta_handler)
        self.assertIsNotNone(final_handler)
        self.assertNotIn("playTts", delta_handler.group(0))
        self.assertIn("playTts(payload.text)", final_handler.group(0))
        self.assertIn("refreshStageContext", final_handler.group(0))

        for key in (
            "stage.sessionTarget",
            "stage.sessionFallback",
            "stage.sessionTargetLoadFailed",
            "stage.roleLabel",
            "stage.modelProfileLabel",
            "stage.modelProfileNone",
            "stage.voiceProfileLabel",
            "stage.live2dProfileLabel",
            "stage.channelLabel",
            "runtimeContext.session",
            "runtimeContext.character",
            "runtimeContext.llm",
            "runtimeContext.voice",
            "runtimeContext.live2d",
            "runtimeContext.channel",
            "runtimeContext.notSet",
            "runtimeContext.internalWeb",
            "messenger.session",
            "messenger.sessionFallback",
            "messenger.channelTargetOption",
            "messenger.sessionLoadFailed",
            "messenger.runtimeContextUnavailable",
            "messenger.uploadFile",
            "messenger.urlInput",
            "messenger.urlPlaceholder",
            "messenger.startRecording",
            "messenger.stopRecording",
            "messenger.recording",
            "messenger.recordingUnsupported",
            "messenger.uploading",
            "messenger.uploadFailed",
            "messenger.attached",
            "messenger.removeAttachment",
            "channelTargets.disabled",
            "channelTargets.notRunning",
        ):
            self.assertGreaterEqual(i18n_js.count(f'"{key}"'), 3)

    def test_stage_live2d_falls_back_before_noisy_webgl_initialization(self) -> None:
        stage_js = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn("canUsePixiLive2D()", stage_js)
        self.assertIn("canCreateWebGLShaderProgram()", stage_js)
        self.assertIn('"stage.fallback.webglUnavailable"', stage_js)
        self.assertIn("withPixiInitializationGuard", stage_js)
        self.assertIn("isKnownPixiInitializationNoise", stage_js)
        self.assertIn("destroyLive2DApp()", stage_js)
        self.assertIn('"stage.fallback.webglUnavailable"', i18n_js)

    def test_character_profiles_page_is_registered_and_translated(self) -> None:
        app_routes = (WEB_ROOT.parents[0] / "web_pages.py").read_text(encoding="utf-8")
        admin_html = (WEB_ROOT / "admin.html").read_text(encoding="utf-8")
        characters_html = (WEB_ROOT / "characters.html").read_text(encoding="utf-8")
        characters_js = (WEB_ROOT / "characters-app.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('WebPageRoute("/admin/characters"', app_routes)
        self.assertIn('href="/admin/characters"', admin_html)
        self.assertIn('data-i18n-key="admin.characters"', admin_html)
        self.assertIn('id="character-profile-form"', characters_html)
        self.assertIn('id="character-model-profile"', characters_html)
        self.assertIn('id="character-llm-model"', characters_html)
        self.assertIn('id="character-voice-profile"', characters_html)
        self.assertIn('id="character-live2d-profile"', characters_html)
        self.assertIn('id="character-default-channel-type"', characters_html)
        self.assertIn('id="character-default-channel-integration"', characters_html)
        self.assertIn('id="character-emotion-map"', characters_html)
        self.assertIn('id="character-emotion-map-add"', characters_html)
        self.assertIn('id="character-expression-options"', characters_html)
        self.assertIn('id="character-motion-options"', characters_html)
        self.assertIn('id="character-profile-export"', characters_html)
        self.assertIn('id="character-package-import"', characters_html)
        self.assertIn('id="character-package-json"', characters_html)
        self.assertIn('id="character-package-import-name"', characters_html)
        self.assertIn('id="character-package-overwrite"', characters_html)
        self.assertIn('"/api/character-profiles"', characters_js)
        self.assertIn('"/api/web/config"', characters_js)
        self.assertIn('"/api/channel-integrations"', characters_js)
        self.assertIn("exportSelectedCharacter", characters_js)
        self.assertIn("importCharacterPackage", characters_js)
        self.assertIn("collectEmotionMaps", characters_js)
        self.assertIn("live2dModelForCharacter", characters_js)
        self.assertIn("renderChannelTypeOptions", characters_js)
        self.assertIn("renderChannelIntegrationOptions", characters_js)
        self.assertIn("syncChannelTypeFromIntegration", characters_js)
        self.assertIn('"characters.heading"', i18n_js)
        self.assertIn('"characters.bindingHelp"', i18n_js)
        self.assertIn('"characters.modelProfile"', i18n_js)
        self.assertIn('"characters.llmModel"', i18n_js)
        self.assertIn('"characters.voiceProfile"', i18n_js)
        self.assertIn('"characters.live2dProfile"', i18n_js)
        self.assertIn('"characters.defaultChannelType"', i18n_js)
        self.assertIn('"characters.defaultChannelIntegration"', i18n_js)
        self.assertIn('"characters.noDefaultChannel"', i18n_js)
        self.assertIn('"characters.noDefaultIntegration"', i18n_js)
        self.assertIn('"characters.effectiveProfile"', i18n_js)
        self.assertIn('"characters.emotionMapTitle"', i18n_js)
        self.assertIn('"characters.emotionMapCount"', i18n_js)
        self.assertIn('"characters.exportPackage"', i18n_js)
        self.assertIn('"characters.importPackageTitle"', i18n_js)

    def test_session_centered_admin_model_pages_are_split(self) -> None:
        app_routes = (WEB_ROOT.parents[0] / "web_pages.py").read_text(encoding="utf-8")
        admin_html = (WEB_ROOT / "admin.html").read_text(encoding="utf-8")
        models_html = (WEB_ROOT / "models.html").read_text(encoding="utf-8")
        voice_html = (WEB_ROOT / "voice-models.html").read_text(encoding="utf-8")
        live2d_html = (WEB_ROOT / "live2d.html").read_text(encoding="utf-8")
        sessions_html = (WEB_ROOT / "sessions.html").read_text(encoding="utf-8")
        characters_html = (WEB_ROOT / "characters.html").read_text(encoding="utf-8")
        openwebui_html = (WEB_ROOT / "openwebui.html").read_text(encoding="utf-8")
        guide_html = (WEB_ROOT / "guide.html").read_text(encoding="utf-8")
        structure_html = (WEB_ROOT / "structure.html").read_text(encoding="utf-8")
        models_js = (WEB_ROOT / "models-app.js").read_text(encoding="utf-8")
        voice_js = (WEB_ROOT / "voice-models-app.js").read_text(encoding="utf-8")
        live2d_js = (WEB_ROOT / "live2d-app.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('WebPageRoute("/admin/voice-models"', app_routes)
        self.assertIn('WebPageRoute("/admin/live2d"', app_routes)
        self.assertIn('href="/admin/voice-models"', admin_html)
        self.assertIn('href="/admin/live2d"', admin_html)
        expected_links_by_page = {
            "sessions": (sessions_html, ("/admin/models", "/admin/voice-models", "/admin/live2d", "/admin/openwebui")),
            "characters": (characters_html, ("/admin/models", "/admin/voice-models", "/admin/live2d", "/admin/openwebui")),
            "models": (models_html, ("/admin/voice-models", "/admin/live2d", "/admin/openwebui")),
            "voice": (voice_html, ("/admin/models", "/admin/live2d", "/admin/openwebui")),
            "live2d": (live2d_html, ("/admin/models", "/admin/voice-models", "/admin/openwebui")),
            "openwebui": (openwebui_html, ("/admin/models", "/admin/voice-models", "/admin/live2d")),
            "guide": (guide_html, ("/admin/models", "/admin/voice-models", "/admin/live2d", "/admin/openwebui")),
            "structure": (structure_html, ("/admin/models", "/admin/voice-models", "/admin/live2d", "/admin/openwebui")),
        }
        for _page_name, (html, expected_links) in expected_links_by_page.items():
            for href in expected_links:
                self.assertIn(f'href="{href}"', html)
        self.assertIn('data-i18n-key="admin.llmModels"', admin_html)
        self.assertIn('id="model-chat-model"', models_html)
        self.assertNotIn('id="model-tts-provider"', models_html)
        self.assertNotIn('id="model-asr-provider"', models_html)
        self.assertNotIn('id="model-live2d-selection"', models_html)
        self.assertNotIn('model-tts-', models_js)
        self.assertNotIn('model-asr-', models_js)
        self.assertNotIn('model-live2d-', models_js)
        self.assertNotIn('tts: {', models_js)
        self.assertNotIn('asr: {', models_js)
        self.assertNotIn('live2d: {', models_js)
        self.assertIn('id="voice-profile-label"', voice_html)
        self.assertIn('id="voice-tts-provider"', voice_html)
        self.assertIn('id="voice-stt-provider"', voice_html)
        self.assertIn('id="live2d-profile-label"', live2d_html)
        self.assertIn('id="live2d-profile-create"', live2d_html)
        self.assertIn('id="live2d-profile-delete"', live2d_html)
        self.assertIn('id="live2d-selection"', live2d_html)
        self.assertIn('label: DOM.label.value', voice_js)
        self.assertIn('label: DOM.label.value', live2d_js)
        self.assertIn('"/api/voice-models"', voice_js)
        self.assertIn('"/api/live2d-models"', live2d_js)
        self.assertIn('"/api/model-profiles"', voice_js)
        self.assertIn('"/api/model-profiles"', live2d_js)
        self.assertIn("createProfileFromSelection", live2d_js)
        self.assertIn("deleteSelectedProfile", live2d_js)
        self.assertIn("statusPayload.security_warnings", openwebui_html + (WEB_ROOT / "openwebui-app.js").read_text(encoding="utf-8"))

        for key in (
            "admin.llmModels",
            "admin.voiceModels",
            "admin.live2d",
            "voiceModels.heading",
            "voiceModels.description",
            "live2dAdmin.heading",
            "live2dAdmin.description",
            "live2dAdmin.catalog",
            "openwebui.allowedTargets",
            "openwebui.requireTargetUser",
            "openwebui.security",
        ):
            self.assertGreaterEqual(i18n_js.count(f'"{key}"'), 3)

    def test_channels_page_has_edit_and_smoke_controls(self) -> None:
        channels_js = (WEB_ROOT / "channels-app.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('buildEditableChannelCard', channels_js)
        self.assertIn('/api/channels/definitions', channels_js)
        self.assertIn('/api/channels/config', channels_js)
        self.assertIn('/api/channels/${encodeURIComponent(channelName)}/smoke', channels_js)
        self.assertIn("buildChannelHints", channels_js)
        self.assertIn("buildLocalTestControls", channels_js)
        self.assertIn("runLocalE2ETest", channels_js)
        self.assertIn("/local-test-message", channels_js)
        self.assertIn("POST /api/channels/discord/webhook", channels_js)
        self.assertIn("X-EchoBot-Discord-Secret", channels_js)
        self.assertIn("Native bot events require discord.py", channels_js)
        self.assertIn('i18n.t("channels.saveChanges")', channels_js)
        self.assertIn('i18n.t("channels.reload")', channels_js)
        self.assertIn('i18n.t("channels.smokeTest")', channels_js)
        self.assertIn("drop_pending_updates", channels_js)

        self.assertIn('"channels.saveChanges"', i18n_js)
        self.assertIn('"channels.reload"', i18n_js)
        self.assertIn('"channels.smokeTest"', i18n_js)

    def test_channels_i18n_keys_cover_multiple_languages(self) -> None:
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")
        required_keys = [
            "channels.fieldEnabled",
            "channels.fieldAllowFrom",
            "channels.fieldAllowFromPlaceholder",
            "channels.fieldMirrorToStage",
            "channels.fieldStageSessionName",
            "channels.fieldBotToken",
            "channels.fieldProxy",
            "channels.fieldReplyToMessage",
            "channels.fieldDropPendingUpdates",
            "channels.fieldWebhookSecret",
            "channels.fieldWebhookUrl",
            "channels.fieldChannelId",
            "channels.fieldApiId",
            "channels.fieldAppId",
            "channels.fieldApplicationId",
            "channels.fieldGuildId",
            "channels.localTestTitle",
            "channels.localTestHelp",
            "channels.localSender",
            "channels.localChat",
            "channels.localSession",
            "channels.localText",
            "channels.localTestRun",
            "channels.localTestRunning",
            "channels.localTestAccepted",
            "channels.localTestFailed",
            "channels.secretConfigured",
            "channels.secretNotConfigured",
            "channels.saveChanges",
            "channels.reload",
            "channels.smokeTest",
            "channels.saving",
            "channels.saved",
            "channels.saveFailed",
            "channels.smokeRunning",
            "channels.smokeStarted",
            "channels.smokeOk",
            "channels.smokeFailed",
            "channels.ok",
            "channels.fail",
            "channels.unknown",
            "channels.web",
            "channels.telegram",
            "channels.discord",
            "channels.line",
            "channels.whatsapp",
            "channels.qq",
        ]
        for key in required_keys:
            self.assertGreaterEqual(i18n_js.count(f'"{key}"'), 3)


if __name__ == "__main__":
    unittest.main()

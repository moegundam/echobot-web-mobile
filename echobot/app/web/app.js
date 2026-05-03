import {
    cancelChatJob,
    deleteAttachment,
    requestChatJob,
    requestChatJobTrace,
    requestChatStream,
    requestJson,
    responseToError,
    uploadChatFile,
    uploadChatImage,
} from "./modules/api.js";
import { wireAppEvents } from "./bootstrap/wire-events.js?v=site-public-6";
import { createUiStatusController } from "./bootstrap/ui-status.js?v=site-public-6";
import { appState } from "./core/store.js";
import { createAsrModule } from "./features/asr.js?v=site-public-6";
import { createChatModule } from "./features/chat/index.js?v=site-public-6";
import { createLayoutModule } from "./features/layout/index.js?v=site-public-6";
import { createLive2DModule } from "./features/live2d/index.js?v=site-public-6";
import { createRolesModule } from "./features/roles.js?v=site-public-6";
import { createSessionsModule } from "./features/sessions.js?v=site-public-6";
import { createTtsModule } from "./features/tts.js?v=site-public-6";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { initShellI18n } from "./shell-i18n.js?v=site-public-6";
import {
    MODEL_PROFILE_UPDATE_STORAGE_KEY,
    activeModelProfileFromConfig,
    applyModelProfileToLocalPreferences,
    modelProfileScopeFromConfig,
} from "./model-profile-runtime.js?v=model-profile-2";
import {
    addMessage,
    addSystemMessage,
    clearMessages,
    configureMessageI18n,
    initializeMessageInteractions,
    refreshMessagesLocalizedText,
    removeMessage,
    updateMessage,
} from "./modules/messages.js?v=site-public-6";
import { createTraceModule } from "./modules/traces.js?v=site-public-6";
import {
    clamp,
    delay,
    formatTimestamp,
    normalizeSessionName,
    roundTo,
    smoothValue,
} from "./modules/utils.js";

const status = createUiStatusController();
let currentActiveModelProfile = null;
const i18n = initShellI18n({
    onChange: () => {
        displayMode.refresh();
        layout?.refreshSidebarLabels?.();
        layout?.refreshLocalizedText?.();
        live2d?.refreshLocalizedText?.();
        tts?.refreshLocalizedText?.();
        asr?.refreshLocalizedText?.();
        sessions?.refreshLocalizedText?.();
        roles?.refreshLocalizedText?.();
        traces?.refreshLocalizedText?.();
        chat?.refreshLocalizedText?.();
        refreshMessagesLocalizedText();
        status.refreshLocalizedText?.(i18n.t);
        renderActiveModelProfile(currentActiveModelProfile);
    },
});
configureMessageI18n({ t: i18n.t });
const displayMode = initShellDisplayMode({ t: i18n.t });
let currentModelProfileScope = "";
window.addEventListener("storage", (event) => {
    if (event.key === MODEL_PROFILE_UPDATE_STORAGE_KEY) {
        const eventScope = parseModelProfileUpdateScope(event.newValue);
        if (
            eventScope
            && currentModelProfileScope
            && eventScope !== currentModelProfileScope
        ) {
            return;
        }
        window.location.reload();
    }
});
const layout = createLayoutModule({
    addMessage,
    formatTimestamp,
    t: i18n.t,
    requestJson,
    setRunStatus: status.setRunStatus,
});
const live2d = createLive2DModule({
    clamp,
    requestJson,
    roundTo,
    responseToError,
    setRunStatus: status.setRunStatus,
    t: i18n.t,
});
const tts = createTtsModule({
    addMessage,
    applyMouthValue: live2d.applyMouthValue,
    clamp,
    requestJson,
    responseToError,
    setConnectionState: status.setConnectionState,
    setRunStatus: status.setRunStatus,
    smoothValue,
    t: i18n.t,
});
const asr = createAsrModule({
    addSystemMessage,
    clamp,
    delay,
    ensureAudioContextReady: tts.ensureAudioContextReady,
    requestJson,
    responseToError,
    setRunStatus: status.setRunStatus,
    stopSpeechPlayback: tts.stopSpeechPlayback,
    t: i18n.t,
});

tts.bindHooks({
    syncAlwaysListenPauseState: asr.syncAlwaysListenPauseState,
    updateVoiceInputControls: asr.updateVoiceInputControls,
});

const sessions = createSessionsModule({
    addMessage,
    addSystemMessage,
    clearMessages,
    formatTimestamp,
    normalizeSessionName,
    requestJson,
    speakText: tts.speakText,
    setRunStatus: status.setRunStatus,
    stopSpeechPlayback: tts.stopSpeechPlayback,
    t: i18n.t,
});
const roles = createRolesModule({
    addMessage,
    normalizeSessionName,
    requestJson,
    setRunStatus: status.setRunStatus,
    t: i18n.t,
});
const traces = createTraceModule({ t: i18n.t });
const chat = createChatModule({
    addMessage,
    applySessionSummaries: sessions.applySessionSummaries,
    cancelChatJob,
    createSpeechSession: tts.createSpeechSession,
    drainVoicePromptQueue: asr.drainVoicePromptQueue,
    deleteAttachment,
    ensureAudioContextReady: tts.ensureAudioContextReady,
    finalizeSpeechSession: tts.finalizeSpeechSession,
    normalizeSessionName,
    queueSpeechSessionText: tts.queueSpeechSessionText,
    removeMessage,
    requestChatJob,
    requestChatJobTrace,
    requestChatStream,
    requestSessionSummaries: sessions.requestSessionSummaries,
    resetTracePanel: traces.resetTracePanel,
    setActiveBackgroundJob: status.setActiveBackgroundJob,
    setChatBusy: status.setChatBusy,
    setRunStatus: status.setRunStatus,
    speakText: tts.speakText,
    startTracePanel: traces.startTracePanel,
    stopSpeechPlayback: tts.stopSpeechPlayback,
    syncCurrentSessionFromServer: sessions.syncCurrentSessionFromServer,
    uploadChatFile,
    uploadChatImage,
    applyTracePayload: traces.applyTracePayload,
    updateMessage,
});

status.bindFeatures({
    asr,
    chat,
    roles,
    sessions,
});

sessions.bindRoleHooks({
    closeRoleEditor: roles.closeRoleEditor,
    syncRolePanelForCurrentSession: roles.syncRolePanelForCurrentSession,
});
roles.bindSessionHooks({
    applySessionDetail: sessions.applySessionDetail,
});

document.addEventListener("DOMContentLoaded", initializePage);

async function initializePage() {
    layout.ensureSidebarToggleButtons();
    layout.initializeLive2DDrawer();
    layout.initializePageSplit();
    initializeMessageInteractions();
    wireAppEvents({
        asr,
        chat,
        layout,
        live2d,
        roles,
        sessions,
        status,
        t: i18n.t,
        tts,
    });

    layout.restoreSettingsPanelState();
    layout.restoreCronPanelState();
    layout.restoreHeartbeatPanelState();
    layout.restoreLive2DPanelState();
    layout.restoreRuntimePanelState();
    layout.restoreStageBackgroundPanelState();
    layout.restoreStageEffectsPanelState();
    layout.handleSettingsPanelToggle();
    live2d.setStageMessage(i18n.t("console.live2dLoading"));
    addSystemMessage(i18n.t("console.status.connecting"));

    try {
        const config = await requestJson("/api/web/config");
        currentModelProfileScope = modelProfileScopeFromConfig(config);
        const activeModelProfile = activeModelProfileFromConfig(config);
        currentActiveModelProfile = activeModelProfile;
        applyModelProfileToLocalPreferences(activeModelProfile);
        renderActiveModelProfile(activeModelProfile);
        appState.config = config;
        layout.applyRuntimeConfig(config.runtime);
        const activeLive2DConfig = live2d.applyConfigToUI(config);

        live2d.initializePixiApplication();
        const live2dLoadPromise = live2d.loadLive2DModel(activeLive2DConfig);
        live2d.renderLive2DControls(activeLive2DConfig);
        await live2dLoadPromise;
        live2d.renderLive2DControls(appState.config.live2d);
        layout.restoreSessionSidebarState();
        layout.restoreRoleSidebarState();
        await sessions.initializeSessionPanel(config.session_name);
        await roles.initializeRolePanel();
        await tts.loadTtsOptions(config.tts);
        asr.applyAsrStatus(config.asr);
        asr.startAsrStatusPolling();
        traces.resetTracePanel();

        status.setConnectionState("ready", i18n.t("console.status.ready"), "console.status.ready");
        status.setRunStatus(i18n.t("console.ready"), "console.ready");
        status.setActiveBackgroundJob("");
    } catch (error) {
        console.error(error);
        status.setConnectionState("error", i18n.t("console.status.error"), "console.status.error");
        status.setRunStatus(error.message || i18n.t("console.status.error"));
        live2d.setStageMessage(error.message || i18n.t("console.status.error"));
        addSystemMessage(`${i18n.t("console.status.error")}: ${error.message || error}`);
    }
}

function parseModelProfileUpdateScope(value) {
    try {
        const payload = JSON.parse(String(value || "{}"));
        return String(payload.scope || "").trim();
    } catch (_error) {
        return "";
    }
}

function renderActiveModelProfile(profile) {
    const badge = document.getElementById("model-profile-badge");
    const link = document.getElementById("model-profile-link");
    if (!badge || !link) {
        return;
    }

    if (!profile) {
        badge.hidden = true;
        return;
    }

    const profileId = String(profile.profile_id || "").trim();
    const code = profileId ? profileId.toUpperCase() : "";
    const label = String(profile.label || code || i18n.t("models.defaultProfile")).trim();
    link.textContent = code ? `${code} · ${label}` : label;
    badge.hidden = false;
}

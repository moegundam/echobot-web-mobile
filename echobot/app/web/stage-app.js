import { initShellI18n } from "./shell-i18n.js?v=session-runtime-p1-3&uiux=3";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import { initShellAccessContext } from "./shell-access.js?v=rbac-nav-1";
import {
    initShellSessionLinks,
    rememberShellSessionName,
} from "./shell-session-links.js?v=site-public-6";
import { createStageEventController } from "./features/stage/events.js?stage-modular-2";
import { createStageInteractionController } from "./features/stage/interaction.js?stage-modular-1";
import { createStageLive2DController } from "./features/stage/live2d.js?stage-modular-1";
import { createStageMenuController } from "./features/stage/menu.js?stage-modular-2";
import { createStageRuntimeController } from "./features/stage/runtime.js?stage-modular-1&session-fallback=1";
import { createStageSpeechController } from "./features/stage/speech.js?stage-modular-1";


const subtitleElement = document.getElementById("stage-subtitle");
const subtitleAnnouncementElement = document.getElementById("stage-announcement");
const sessionLabelElement = document.getElementById("stage-session-label");
const sessionSelect = document.getElementById("stage-session-select");
const statusElement = document.getElementById("stage-status");
const audioButton = document.getElementById("stage-audio-enable");
const subtitlePanel = document.getElementById("stage-subtitle-panel");
const subtitleToggleButton = document.getElementById("stage-subtitle-toggle");
const menuToggleButton = document.getElementById("stage-menu-toggle");
const menuCloseButton = document.getElementById("stage-menu-close");
const zoomOutButton = document.getElementById("stage-zoom-out");
const zoomResetButton = document.getElementById("stage-zoom-reset");
const zoomInButton = document.getElementById("stage-zoom-in");
const fullscreenToggleButton = document.getElementById("stage-fullscreen-toggle");
const controlsAutoHideCheckbox = document.getElementById("stage-controls-auto-hide");
const menuBackdrop = document.getElementById("stage-menu-backdrop");
const menuPanel = document.getElementById("stage-menu-panel");
const stageSurface = document.getElementById("stage-surface");
const stageBackgroundImage = document.getElementById("stage-background-image");
const canvasHost = document.getElementById("stage-canvas-host");
const stageToolbar = document.querySelector(".stage-toolbar");
const stageRoleLabel = document.getElementById("stage-role-label");
const stageModelProfileLabel = document.getElementById("stage-model-profile-label");
const stageVoiceProfileLabel = document.getElementById("stage-voice-profile-label");
const stageLive2DProfileLabel = document.getElementById("stage-live2d-profile-label");
const stageChannelLabel = document.getElementById("stage-channel-label");

let sessionName = resolveSessionName();
let subtitleText = "";
let subtitleIsPlaceholder = true;
let currentStatusKey = "stage.status.connecting";
let displayMode;
let interactionController;

rememberShellSessionName(sessionName);
initShellSessionLinks();

const i18n = initShellI18n({
    onChange: () => {
        refreshLocalizedStageText();
        displayMode?.refresh();
    },
});
displayMode = initShellDisplayMode({ t: i18n.t });
void initShellAccessContext({ t: i18n.t });

const stageElements = {
    canvasHost,
    channelLabelElement: stageChannelLabel,
    controlsAutoHideCheckbox,
    fullscreenToggleButton,
    live2dProfileLabelElement: stageLive2DProfileLabel,
    menuBackdrop,
    menuCloseButton,
    menuPanel,
    menuToggleButton,
    modelProfileLabelElement: stageModelProfileLabel,
    roleLabelElement: stageRoleLabel,
    sessionLabelElement,
    sessionSelect,
    stageBackgroundImage,
    stageSurface,
    stageToolbar,
    subtitlePanel,
    subtitleToggleButton,
    voiceProfileLabelElement: stageVoiceProfileLabel,
};

function setStatus(key) {
    currentStatusKey = key;
    if (statusElement) {
        statusElement.textContent = i18n.t(key);
        statusElement.dataset.statusKey = key;
    }
}

const live2dController = createStageLive2DController({
    canvasHost,
    getContext: () => runtimeController?.getContext(),
    getSessionName: () => sessionName,
    i18n,
    onStatus: setStatus,
    zoomInButton,
    zoomOutButton,
    zoomResetButton,
});

const menuController = createStageMenuController({
    elements: stageElements,
    i18n,
    onZoomKeyDown: (event) => interactionController?.handleStageZoomKeyDown(event),
});

interactionController = createStageInteractionController({
    canvasHost,
    isMenuOpen: () => menuController.isStageMenuOpen(),
    live2d: live2dController,
    stageSurface,
    zoomInButton,
    zoomOutButton,
    zoomResetButton,
});

const speechController = createStageSpeechController({
    audioButton,
    getContext: () => runtimeController?.getContext(),
    getSessionName: () => sessionName,
    i18n,
    live2d: live2dController,
    onStatus: setStatus,
});

const eventController = createStageEventController({
    announceSubtitle,
    appendSubtitle,
    applyVisualState: (payload) => live2dController.applyVisualState(payload),
    getSessionName: () => sessionName,
    playTts: (text) => speechController.playTts(text),
    refreshStageContext: (options) => runtimeController.refreshStageContext(options),
    setStatus,
    setSubtitle,
});

const runtimeController = createStageRuntimeController({
    elements: stageElements,
    getLive2DKey: () => live2dController.getKey(),
    i18n,
    initialSessionName: sessionName,
    onLive2DChanged: () => live2dController.reloadFromContext(),
    onSessionChanged: handleSessionChanged,
    onStatus: setStatus,
});

function resolveSessionName() {
    const params = new URLSearchParams(window.location.search);
    return String(params.get("session_name") || "default").trim() || "default";
}

function handleSessionChanged(nextSessionName, options = {}) {
    sessionName = rememberShellSessionName(nextSessionName);
    updateSessionUrl(sessionName);
    initShellSessionLinks();
    if (options.reconnect) {
        void speechController.cancelPlayback?.();
        setSubtitle("");
        setStatus("stage.status.connecting");
        initStageEvents();
    }
}

function updateSessionUrl(nextSessionName) {
    try {
        const url = new URL(window.location.href);
        url.searchParams.set("session_name", nextSessionName);
        window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    } catch (_error) {
        // URL replacement is a convenience only.
    }
}

function setSubtitle(value) {
    subtitleText = String(value || "");
    subtitleIsPlaceholder = !subtitleText;
    if (subtitleElement) {
        subtitleElement.textContent = subtitleText || i18n.t("stage.waiting");
        subtitleElement.scrollTop = subtitleElement.scrollHeight;
    }
}

function appendSubtitle(delta) {
    setSubtitle(`${subtitleText}${String(delta || "")}`);
}

function announceSubtitle(value) {
    if (!subtitleAnnouncementElement) {
        return;
    }
    const text = String(value || "").trim();
    if (!text) {
        return;
    }
    subtitleAnnouncementElement.textContent = "";
    window.setTimeout(() => {
        subtitleAnnouncementElement.textContent = text;
    }, 0);
}

function initStageEvents() {
    eventController.init();
}

function setStageMenuOpen(isOpen, options = {}) {
    menuController.setStageMenuOpen(isOpen, options);
}

function setSubtitlesHidden(hidden, options = {}) {
    menuController.setSubtitlesHidden(hidden, options);
}

function refreshLocalizedStageText() {
    runtimeController.refreshLocalizedText();
    menuController.refreshLocalizedText();
    speechController.refreshLocalizedText();
    live2dController.refreshLocalizedText();
    if (statusElement) {
        statusElement.textContent = i18n.t(currentStatusKey);
    }
    if (subtitleElement && subtitleIsPlaceholder) {
        subtitleElement.textContent = i18n.t("stage.waiting");
    }
}

async function init() {
    setSubtitlesHidden(menuController.getSubtitlesHidden(), { persist: false });
    setStageMenuOpen(false, { restoreFocus: false });
    setStatus("stage.status.connecting");
    menuController.bind();
    interactionController.bind();
    speechController.bind();
    await runtimeController.init();
    initStageEvents();
    await live2dController.reloadFromContext();
}

sessionSelect?.addEventListener("change", () => {
    void runtimeController.setActiveSessionName(sessionSelect.value, { reconnect: true });
});

refreshLocalizedStageText();
init();

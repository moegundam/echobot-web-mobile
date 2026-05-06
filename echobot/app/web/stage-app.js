import { initShellI18n } from "./shell-i18n.js?v=stage-menu-1";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import {
    initShellSessionLinks,
    rememberShellSessionName,
} from "./shell-session-links.js?v=site-public-6";
import {
    fetchSessionRuntimeContext,
    runtimeContextValue,
} from "./session-runtime-context.js?v=session-runtime-context-1";

const subtitleElement = document.getElementById("stage-subtitle");
const sessionLabelElement = document.getElementById("stage-session-label");
const roleLabelElement = document.getElementById("stage-role-label");
const modelProfileLabelElement = document.getElementById("stage-model-profile-label");
const voiceProfileLabelElement = document.getElementById("stage-voice-profile-label");
const live2dProfileLabelElement = document.getElementById("stage-live2d-profile-label");
const channelLabelElement = document.getElementById("stage-channel-label");
const sessionSelect = document.getElementById("stage-session-select");
const statusElement = document.getElementById("stage-status");
const audioButton = document.getElementById("stage-audio-enable");
const subtitlePanel = document.getElementById("stage-subtitle-panel");
const subtitleToggleButton = document.getElementById("stage-subtitle-toggle");
const menuToggleButton = document.getElementById("stage-menu-toggle");
const menuCloseButton = document.getElementById("stage-menu-close");
const menuBackdrop = document.getElementById("stage-menu-backdrop");
const menuPanel = document.getElementById("stage-menu-panel");
const canvasHost = document.getElementById("stage-canvas-host");

const DEFAULT_LIP_SYNC_IDS = ["ParamMouthOpenY", "PARAM_MOUTH_OPEN_Y", "MouthOpenY"];
const STAGE_CONTEXT_REFRESH_INTERVAL_MS = 5000;
const STAGE_SUBTITLE_STORAGE_KEY = "echobot.stage.subtitles.hidden";
let sessionName = resolveSessionName();
rememberShellSessionName(sessionName);
initShellSessionLinks();
let subtitleText = "";
let audioUnlocked = false;
let currentStatusKey = "stage.status.connecting";
let subtitleIsPlaceholder = true;
let stageEventSource = null;
let stageTargets = [];
let stageContext = null;
let audioElement = null;
let activeAudioUrl = "";
let audioContext = null;
let audioSourceNode = null;
let audioAnalyser = null;
let volumeBuffer = null;
let lipSyncFrameId = 0;
let currentMouthValue = 0;
let live2dApp = null;
let live2dModel = null;
let live2dConfig = null;
let live2dLoadPromise = null;
let stageContextRefreshTimerId = 0;
let activeStageExpressionDefinition = null;
let stageExpressionHook = null;
let subtitlesHidden = readStoredSubtitlesHidden();
const expressionDataCache = new Map();
const i18n = initShellI18n({
    onChange: () => {
        refreshLocalizedStageText();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });

refreshLocalizedStageText();

if (audioButton) {
    audioButton.addEventListener("click", async () => {
        audioUnlocked = true;
        audioButton.disabled = true;
        updateAudioButtonText();
        await ensureAudioContextReady();
        setStatus("stage.status.audioReady");
        await stopCurrentAudio();
    });
}

if (subtitleToggleButton) {
    subtitleToggleButton.addEventListener("click", () => {
        setSubtitlesHidden(!subtitlesHidden);
    });
}

if (menuToggleButton) {
    menuToggleButton.addEventListener("click", () => {
        setStageMenuOpen(true);
    });
}

if (menuCloseButton) {
    menuCloseButton.addEventListener("click", () => {
        setStageMenuOpen(false);
    });
}

if (menuBackdrop) {
    menuBackdrop.addEventListener("click", () => {
        setStageMenuOpen(false);
    });
}

window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isStageMenuOpen()) {
        setStageMenuOpen(false);
    }
});

if (sessionSelect) {
    sessionSelect.addEventListener("change", () => {
        void setActiveSessionName(sessionSelect.value, { reconnect: true });
    });
}

init();

async function init() {
    setSubtitlesHidden(subtitlesHidden, { persist: false });
    setStageMenuOpen(false, { restoreFocus: false });
    setStatus("stage.status.connecting");
    await loadStageTargets();
    await loadStageContext();
    startStageContextRefresh();
    initStageEvents();
    await reloadLive2DFromContext();
}

function resolveSessionName() {
    const params = new URLSearchParams(window.location.search);
    return String(params.get("session_name") || "default").trim() || "default";
}

function setStatus(key) {
    currentStatusKey = key;
    if (statusElement) {
        statusElement.textContent = i18n.t(key);
        statusElement.dataset.statusKey = key;
    }
}

function setStageMenuOpen(isOpen, options = {}) {
    const open = Boolean(isOpen);
    if (menuPanel) {
        menuPanel.setAttribute("aria-hidden", open ? "false" : "true");
    }
    if (menuToggleButton) {
        menuToggleButton.setAttribute("aria-expanded", open ? "true" : "false");
        menuToggleButton.textContent = i18n.t(open ? "stage.menu.close" : "stage.menu.open");
    }
    if (menuBackdrop) {
        menuBackdrop.hidden = !open;
    }
    document.documentElement.classList.toggle("stage-menu-open", open);
    if (!open && menuToggleButton && options.restoreFocus !== false) {
        menuToggleButton.focus({ preventScroll: true });
    }
}

function isStageMenuOpen() {
    return Boolean(menuPanel && menuPanel.getAttribute("aria-hidden") === "false");
}

function setSubtitlesHidden(hidden, options = {}) {
    subtitlesHidden = Boolean(hidden);
    if (subtitlePanel) {
        subtitlePanel.hidden = subtitlesHidden;
    }
    if (subtitleToggleButton) {
        subtitleToggleButton.setAttribute("aria-pressed", subtitlesHidden ? "true" : "false");
        subtitleToggleButton.textContent = i18n.t(
            subtitlesHidden ? "stage.subtitle.show" : "stage.subtitle.hide",
        );
    }
    document.documentElement.classList.toggle("stage-subtitles-hidden", subtitlesHidden);
    if (options.persist !== false) {
        writeStoredSubtitlesHidden(subtitlesHidden);
    }
}

async function setActiveSessionName(value, options = {}) {
    sessionName = rememberShellSessionName(
        String(value || "").trim() || "default",
    );
    updateSessionLabel();
    if (sessionSelect && sessionSelect.value !== sessionName) {
        sessionSelect.value = sessionName;
    }
    updateSessionUrl(sessionName);
    initShellSessionLinks();
    const live2dChanged = await loadStageContext();
    if (live2dChanged) {
        await reloadLive2DFromContext();
    }
    if (options.reconnect) {
        setSubtitle("");
        setStatus("stage.status.connecting");
        initStageEvents();
    }
}

async function loadStageTargets() {
    if (!sessionSelect) {
        return;
    }
    try {
        const response = await fetch("/api/channels/stage-targets");
        if (!response.ok) {
            throw await responseToError(response);
        }
        const payload = await response.json();
        stageTargets = Array.isArray(payload.targets) ? payload.targets : [];
        renderStageTargetOptions(stageTargets);
    } catch (error) {
        console.warn("Unable to load stage targets", error);
        stageTargets = [];
        renderStageTargetOptions([]);
        setStatus("stage.sessionTargetLoadFailed");
    }
}

async function loadStageContext() {
    const previousLive2DKey = stageContextLive2DKey();
    try {
        stageContext = await fetchSessionRuntimeContext(sessionName);
    } catch (error) {
        console.warn("Unable to load stage context", error);
        stageContext = null;
        renderStageContext();
        return false;
    }
    renderStageContext();
    return previousLive2DKey !== stageContextLive2DKey();
}

async function refreshStageContext(options = {}) {
    const live2dChanged = await loadStageContext();
    if (live2dChanged && options.reloadLive2D) {
        await reloadLive2DFromContext();
    }
}

function startStageContextRefresh() {
    if (stageContextRefreshTimerId) {
        window.clearInterval(stageContextRefreshTimerId);
    }
    stageContextRefreshTimerId = window.setInterval(() => {
        void refreshStageContext({ reloadLive2D: true });
    }, STAGE_CONTEXT_REFRESH_INTERVAL_MS);
    window.addEventListener("pagehide", () => {
        if (stageContextRefreshTimerId) {
            window.clearInterval(stageContextRefreshTimerId);
            stageContextRefreshTimerId = 0;
        }
    });
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            void refreshStageContext({ reloadLive2D: true });
        }
    });
    window.addEventListener("focus", () => {
        void refreshStageContext({ reloadLive2D: true });
    });
}

function renderStageContext() {
    const context = stageContext && typeof stageContext === "object"
        ? stageContext
        : {};
    const roleName = String(context.role_name || "default");
    if (roleLabelElement) {
        roleLabelElement.textContent = i18n.t("stage.roleLabel", {
            role: roleName,
        });
    }
    if (modelProfileLabelElement) {
        modelProfileLabelElement.textContent = i18n.t("stage.modelProfileLabel", {
            profile: stageModelProfileText(context),
        });
    }
    if (voiceProfileLabelElement) {
        voiceProfileLabelElement.textContent = i18n.t("stage.voiceProfileLabel", {
            profile: runtimeContextValue(context, "voice", i18n.t),
        });
    }
    if (live2dProfileLabelElement) {
        live2dProfileLabelElement.textContent = i18n.t("stage.live2dProfileLabel", {
            profile: runtimeContextValue(context, "live2d", i18n.t),
        });
    }
    if (channelLabelElement) {
        channelLabelElement.textContent = i18n.t("stage.channelLabel", {
            channel: runtimeContextValue(context, "channel", i18n.t),
        });
    }
}

function stageModelProfileText(context) {
    if (context && typeof context === "object" && context.llm_model) {
        return runtimeContextValue(context, "llm", i18n.t);
    }
    const label = String(context.model_profile_label || "").trim();
    const profileId = String(context.model_profile_id || "").trim();
    if (label) {
        return label;
    }
    if (profileId) {
        return profileId;
    }
    return i18n.t("stage.modelProfileNone");
}

function renderStageTargetOptions(targets) {
    if (!sessionSelect) {
        return;
    }
    const options = buildStageTargetOptions(targets, sessionName);
    sessionSelect.replaceChildren(...options);
    sessionSelect.value = sessionName;
}

function buildStageTargetOptions(targets, currentSessionName) {
    const options = [];
    const seenSessions = new Set();
    for (const target of targets) {
        const targetSessionName = String((target && target.session_name) || "").trim();
        if (!targetSessionName || seenSessions.has(targetSessionName)) {
            continue;
        }
        seenSessions.add(targetSessionName);
        const option = document.createElement("option");
        option.value = targetSessionName;
        option.textContent = stageTargetLabel(target);
        options.push(option);
    }

    if (!seenSessions.has(currentSessionName)) {
        const fallbackOption = document.createElement("option");
        fallbackOption.value = currentSessionName;
        fallbackOption.textContent = i18n.t("stage.sessionFallback", {
            session: currentSessionName,
        });
        options.unshift(fallbackOption);
    }
    return options;
}

function stageTargetLabel(target) {
    const baseLabel = String(
        (target && target.display_name) || (target && target.session_name) || "default",
    );
    if (target && target.enabled === false) {
        return `${baseLabel} · ${i18n.t("channelTargets.disabled")}`;
    }
    if (target && target.running === false) {
        return `${baseLabel} · ${i18n.t("channelTargets.notRunning")}`;
    }
    return baseLabel;
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

function updateSessionLabel() {
    if (sessionLabelElement) {
        sessionLabelElement.textContent = i18n.t("stage.sessionLabel", {
            session: sessionName,
        });
    }
}

function setSubtitle(value) {
    subtitleText = String(value || "");
    subtitleIsPlaceholder = !subtitleText;
    if (subtitleElement) {
        subtitleElement.textContent = subtitleText || i18n.t("stage.waiting");
    }
}

function appendSubtitle(delta) {
    setSubtitle(`${subtitleText}${String(delta || "")}`);
}

function initStageEvents() {
    if (!window.EventSource) {
        setStatus("stage.status.sseUnavailable");
        return;
    }
    if (stageEventSource) {
        stageEventSource.close();
        stageEventSource = null;
    }

    const url = `/api/stage/events?session_name=${encodeURIComponent(sessionName)}`;
    const source = new EventSource(url);
    stageEventSource = source;

    source.addEventListener("open", () => {
        setStatus("stage.status.live");
    });
    source.addEventListener("error", () => {
        setStatus("stage.status.reconnecting");
    });
    source.addEventListener("assistant_delta", (event) => {
        const payload = parseStageEvent(event);
        appendSubtitle(payload.text);
    });
    source.addEventListener("subtitle", (event) => {
        const payload = parseStageEvent(event);
        applyStageVisualState(payload);
        setSubtitle(payload.text);
    });
    source.addEventListener("assistant_final", async (event) => {
        const payload = parseStageEvent(event);
        applyStageVisualState(payload);
        setSubtitle(payload.text);
        void refreshStageContext({ reloadLive2D: true });
        await playTts(payload.text);
    });
    source.addEventListener("character_state", (event) => {
        const payload = parseStageEvent(event);
        applyStageVisualState(payload);
    });
}

function parseStageEvent(event) {
    try {
        const payload = JSON.parse(event.data || "{}");
        const metadata = payload && typeof payload.metadata === "object" && payload.metadata
            ? payload.metadata
            : {};
        return {
            text: String(payload.text || ""),
            emotion: String(payload.emotion || metadata.emotion || ""),
            expression: String(payload.expression || metadata.expression || ""),
            motion: String(payload.motion || metadata.motion || ""),
        };
    } catch (_error) {
        return {
            text: "",
            emotion: "",
            expression: "",
            motion: "",
        };
    }
}

function applyStageVisualState(payload) {
    if (!payload) {
        return;
    }
    if (payload.expression || payload.emotion) {
        applyStageExpression(payload.expression || payload.emotion);
    }
    if (payload.motion) {
        playStageMotion(payload.motion);
    }
}

async function playTts(text) {
    const spokenText = String(text || "").trim();
    if (!spokenText) {
        return;
    }

    try {
        setStatus("stage.status.tts");
        const response = await fetch("/api/web/tts", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                text: spokenText,
            }),
        });
        if (!response.ok) {
            throw await responseToError(response);
        }

        const audioBlob = await response.blob();
        await stopCurrentAudio();
        if (!audioUnlocked) {
            setStatus("stage.status.tapAudio");
        }
        if (await canUseAudioContext()) {
            await playBlobWithAudioContext(audioBlob);
        } else {
            await playBlobWithHtmlAudio(audioBlob);
        }
        audioUnlocked = true;
        updateAudioButtonText();
    } catch (error) {
        console.warn("TTS playback failed", error);
        setStatus(audioUnlocked ? "stage.status.ttsFailed" : "stage.status.tapAudio");
        if (audioButton && !audioUnlocked) {
            audioButton.disabled = false;
            updateAudioButtonText();
        }
    }
}

async function stopCurrentAudio() {
    if (audioSourceNode) {
        try {
            audioSourceNode.stop();
        } catch (_error) {
            // Source nodes can only be stopped once.
        }
        try {
            audioSourceNode.disconnect();
        } catch (_error) {
            // Already disconnected.
        }
        audioSourceNode = null;
    }
    if (audioAnalyser) {
        try {
            audioAnalyser.disconnect();
        } catch (_error) {
            // Already disconnected.
        }
        audioAnalyser = null;
    }
    volumeBuffer = null;
    stopLipSyncLoop();

    if (audioElement) {
        audioElement.pause();
        audioElement.removeAttribute("src");
        audioElement.load();
        audioElement = null;
    }
    if (activeAudioUrl) {
        URL.revokeObjectURL(activeAudioUrl);
        activeAudioUrl = "";
    }
    applyMouthValue(0);
}

async function playBlobWithHtmlAudio(audioBlob) {
    activeAudioUrl = URL.createObjectURL(audioBlob);
    audioElement = new Audio(activeAudioUrl);
    audioElement.addEventListener("ended", () => {
        setStatus("stage.status.live");
    }, { once: true });
    audioElement.addEventListener("error", () => {
        setStatus("stage.status.audioError");
    }, { once: true });
    await audioElement.play();
}

async function playBlobWithAudioContext(audioBlob) {
    const context = await ensureAudioContextReady();
    if (!context) {
        await playBlobWithHtmlAudio(audioBlob);
        return;
    }

    const arrayBuffer = await audioBlob.arrayBuffer();
    const audioBuffer = await context.decodeAudioData(arrayBuffer.slice(0));
    const sourceNode = context.createBufferSource();
    const analyserNode = context.createAnalyser();
    analyserNode.fftSize = 1024;
    sourceNode.buffer = audioBuffer;
    sourceNode.connect(analyserNode);
    analyserNode.connect(context.destination);

    audioSourceNode = sourceNode;
    audioAnalyser = analyserNode;
    volumeBuffer = new Uint8Array(analyserNode.fftSize);

    const playbackEnded = new Promise((resolve) => {
        sourceNode.onended = resolve;
    });
    startLipSyncLoop();
    sourceNode.start(0);
    await playbackEnded;
    await stopCurrentAudio();
    setStatus("stage.status.live");
}

async function canUseAudioContext() {
    if (!window.AudioContext && !window.webkitAudioContext) {
        return false;
    }
    try {
        return Boolean(await ensureAudioContextReady());
    } catch (error) {
        console.warn("AudioContext unavailable", error);
        return false;
    }
}

async function ensureAudioContextReady() {
    if (!window.AudioContext && !window.webkitAudioContext) {
        return null;
    }
    if (!audioContext) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        audioContext = new AudioContextClass();
    }
    if (audioContext.state === "suspended") {
        await audioContext.resume();
    }
    return audioContext;
}

function startLipSyncLoop() {
    if (!audioAnalyser || !volumeBuffer) {
        return;
    }

    const updateFrame = () => {
        if (!audioAnalyser || !volumeBuffer) {
            return;
        }

        audioAnalyser.getByteTimeDomainData(volumeBuffer);
        let total = 0;
        for (let index = 0; index < volumeBuffer.length; index += 1) {
            const sample = (volumeBuffer[index] - 128) / 128;
            total += sample * sample;
        }

        const rms = Math.sqrt(total / volumeBuffer.length);
        const scaledValue = clamp((rms - 0.02) * 5.4, 0, 1);
        currentMouthValue = smoothValue(currentMouthValue, scaledValue, 0.38);
        applyMouthValue(currentMouthValue);
        lipSyncFrameId = window.requestAnimationFrame(updateFrame);
    };

    stopLipSyncLoop();
    lipSyncFrameId = window.requestAnimationFrame(updateFrame);
}

function stopLipSyncLoop() {
    if (lipSyncFrameId) {
        window.cancelAnimationFrame(lipSyncFrameId);
        lipSyncFrameId = 0;
    }
    currentMouthValue = 0;
}

function applyMouthValue(value) {
    const internalModel = live2dModel && live2dModel.internalModel;
    const coreModel = internalModel && internalModel.coreModel;
    if (!coreModel || typeof coreModel.setParameterValueById !== "function") {
        return;
    }

    const lipSyncIds = Array.isArray(live2dConfig && live2dConfig.lip_sync_parameter_ids)
        && live2dConfig.lip_sync_parameter_ids.length > 0
        ? live2dConfig.lip_sync_parameter_ids
        : DEFAULT_LIP_SYNC_IDS;

    lipSyncIds.forEach((parameterId) => {
        try {
            coreModel.setParameterValueById(parameterId, value);
        } catch (error) {
            console.warn(`Failed to update Live2D mouth parameter ${parameterId}`, error);
        }
    });

    if (live2dConfig && live2dConfig.mouth_form_parameter_id) {
        try {
            coreModel.setParameterValueById(live2dConfig.mouth_form_parameter_id, 0);
        } catch (error) {
            console.warn("Failed to reset Live2D mouth form parameter", error);
        }
    }
}

async function applyStageExpression(expressionName) {
    const expressionItem = findLive2DExpression(expressionName);
    if (!expressionItem || !live2dModel) {
        return;
    }

    try {
        const expressionDefinition = await loadStageExpressionDefinition(expressionItem);
        activeStageExpressionDefinition = expressionDefinition;
        applyActiveStageExpression();
    } catch (error) {
        console.warn("Failed to apply stage expression", error);
    }
}

function applyActiveStageExpression() {
    if (!activeStageExpressionDefinition) {
        return;
    }
    applyStageExpressionDefinition(activeStageExpressionDefinition);
}

function applyStageExpressionDefinition(expressionDefinition) {
    const internalModel = live2dModel && live2dModel.internalModel;
    const coreModel = internalModel && internalModel.coreModel;
    if (!coreModel || typeof coreModel.setParameterValueById !== "function") {
        return;
    }

    expressionDefinition.parameters.forEach((parameter) => {
        try {
            if (parameter.blend === "Add" && typeof coreModel.addParameterValueById === "function") {
                coreModel.addParameterValueById(parameter.id, parameter.value);
                return;
            }
            if (
                parameter.blend === "Multiply"
                && typeof coreModel.multiplyParameterValueById === "function"
            ) {
                coreModel.multiplyParameterValueById(parameter.id, parameter.value);
                return;
            }
            coreModel.setParameterValueById(parameter.id, parameter.value);
        } catch (error) {
            console.warn(`Failed to apply stage expression parameter ${parameter.id}`, error);
        }
    });
}

async function playStageMotion(motionName) {
    const motionItem = findLive2DMotion(motionName);
    if (!motionItem || !live2dModel || typeof live2dModel.motion !== "function") {
        return;
    }

    try {
        await live2dModel.motion(motionItem.group, motionItem.index);
    } catch (error) {
        console.warn("Failed to play stage motion", error);
    }
}

function findLive2DExpression(expressionName) {
    const normalizedName = normalizeStageDirective(expressionName);
    const expressions = live2dConfig && Array.isArray(live2dConfig.expressions)
        ? live2dConfig.expressions
        : [];
    if (!normalizedName || expressions.length === 0) {
        return null;
    }
    return expressions.find((item) => (
        item.url
        && directiveMatchesLive2DItem(item, normalizedName)
    )) || null;
}

function findLive2DMotion(motionName) {
    const normalizedName = normalizeStageDirective(motionName);
    const motions = live2dConfig && Array.isArray(live2dConfig.motions)
        ? live2dConfig.motions
        : [];
    if (!normalizedName || motions.length === 0) {
        return null;
    }
    return motions.find((item) => (
        directiveMatchesLive2DItem(item, normalizedName)
    )) || null;
}

function directiveMatchesLive2DItem(item, normalizedName) {
    if (!item || !normalizedName) {
        return false;
    }
    return [
        item.file,
        item.name,
        item.note,
    ].some((value) => normalizeStageDirective(value) === normalizedName);
}

function normalizeStageDirective(value) {
    return String(value || "").trim().toLowerCase();
}

async function loadStageExpressionDefinition(expressionItem) {
    if (expressionDataCache.has(expressionItem.url)) {
        return expressionDataCache.get(expressionItem.url);
    }

    const response = await fetch(expressionItem.url, {
        cache: "no-store",
    });
    if (!response.ok) {
        throw await responseToError(response);
    }

    const payload = await response.json();
    const parameters = Array.isArray(payload && payload.Parameters)
        ? payload.Parameters
            .filter((item) => item && typeof item === "object")
            .map((item) => ({
                id: String(item.Id || ""),
                value: typeof item.Value === "number" ? item.Value : 0,
                blend: normalizeExpressionBlend(item.Blend),
            }))
            .filter((item) => item.id)
        : [];
    const expressionDefinition = {
        parameters: parameters,
    };
    expressionDataCache.set(expressionItem.url, expressionDefinition);
    return expressionDefinition;
}

function normalizeExpressionBlend(blend) {
    const normalizedBlend = String(blend || "").trim().toLowerCase();
    if (normalizedBlend === "add") {
        return "Add";
    }
    if (normalizedBlend === "multiply") {
        return "Multiply";
    }
    return "Set";
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function smoothValue(previousValue, nextValue, factor) {
    return previousValue + (nextValue - previousValue) * factor;
}

async function initLive2D() {
    if (!canvasHost) {
        return;
    }

    const contextConfig = stageContextLive2DConfig();
    let config = null;
    try {
        config = await fetchWebConfig();
    } catch (error) {
        console.warn("Unable to load web config", error);
        if (!contextConfig) {
            markLive2DUnavailable("stage.fallback.configUnavailable");
            return;
        }
    }

    live2dConfig = normalizeLive2DConfig(
        resolveStageLive2DConfig(contextConfig, config && config.live2d),
        contextConfig ? "session" : "web-config",
    );
    const modelUrl = live2dConfig.model_url;
    canvasHost.dataset.live2dSource = live2dConfig.source;
    canvasHost.dataset.live2dSelectionKey = live2dConfig.selection_key;
    canvasHost.dataset.live2dModelUrl = modelUrl;
    if (!modelUrl) {
        markLive2DUnavailable("stage.fallback.subtitleMode");
        return;
    }

    const live2dReadiness = canUsePixiLive2D();
    if (!live2dReadiness.ready) {
        markLive2DUnavailable(live2dReadiness.messageKey);
        return;
    }

    try {
        await withPixiInitializationGuard(async () => {
            live2dApp = await createPixiApplication(canvasHost);
            live2dModel = await window.PIXI.live2d.Live2DModel.from(modelUrl, {
                autoInteract: false,
            });
            live2dApp.stage.addChild(live2dModel);
            attachStageExpressionHook(live2dModel);
            fitLive2DModel();
            window.addEventListener("resize", fitLive2DModel);
            canvasHost.dataset.live2d = "ready";
            canvasHost.dataset.live2dSource = live2dConfig.source;
            canvasHost.dataset.live2dSelectionKey = live2dConfig.selection_key;
            canvasHost.dataset.live2dModelUrl = modelUrl;
        });
    } catch (error) {
        console.warn("Live2D initialization failed", error);
        markLive2DUnavailable(
            isKnownPixiInitializationNoise([error])
                ? "stage.fallback.webglUnavailable"
                : "stage.fallback.subtitleMode",
        );
    }
}

async function fetchWebConfig() {
    const response = await fetch("/api/web/config");
    if (!response.ok) {
        throw await responseToError(response);
    }
    return response.json();
}

async function reloadLive2DFromContext() {
    if (live2dLoadPromise) {
        return live2dLoadPromise;
    }
    live2dLoadPromise = (async () => {
        destroyLive2DApp();
        if (canvasHost) {
            canvasHost.textContent = "";
            delete canvasHost.dataset.i18nFallbackKey;
        }
        await initLive2D();
    })();
    try {
        await live2dLoadPromise;
    } finally {
        live2dLoadPromise = null;
    }
}

function attachStageExpressionHook(model) {
    detachStageExpressionHook();
    const internalModel = model && model.internalModel;
    if (!internalModel || typeof internalModel.on !== "function") {
        return;
    }
    stageExpressionHook = () => {
        applyActiveStageExpression();
    };
    internalModel.on("beforeModelUpdate", stageExpressionHook);
}

function detachStageExpressionHook() {
    if (!stageExpressionHook || !live2dModel || !live2dModel.internalModel) {
        stageExpressionHook = null;
        return;
    }
    const internalModel = live2dModel.internalModel;
    if (typeof internalModel.off === "function") {
        internalModel.off("beforeModelUpdate", stageExpressionHook);
    }
    stageExpressionHook = null;
}

function canUsePixiLive2D() {
    if (!window.PIXI || !window.PIXI.live2d || !window.PIXI.live2d.Live2DModel) {
        return {
            ready: false,
            messageKey: "stage.fallback.live2dUnavailable",
        };
    }
    if (!canCreateWebGLShaderProgram()) {
        return {
            ready: false,
            messageKey: "stage.fallback.webglUnavailable",
        };
    }
    return {
        ready: true,
        messageKey: "",
    };
}

function canCreateWebGLShaderProgram() {
    const documentRef = window.document;
    if (!documentRef || typeof documentRef.createElement !== "function") {
        return false;
    }

    const canvas = documentRef.createElement("canvas");
    let gl = null;
    try {
        gl = canvas.getContext("webgl2")
            || canvas.getContext("webgl")
            || canvas.getContext("experimental-webgl");
    } catch (_error) {
        return false;
    }
    if (!gl || typeof gl.createShader !== "function") {
        return false;
    }

    const vertexShader = compileWebGLShader(
        gl,
        gl.VERTEX_SHADER,
        "attribute vec2 position; void main(){ gl_Position = vec4(position, 0.0, 1.0); }",
    );
    const fragmentShader = compileWebGLShader(
        gl,
        gl.FRAGMENT_SHADER,
        "void main(){ gl_FragColor = vec4(1.0); }",
    );
    if (!vertexShader || !fragmentShader) {
        deleteWebGLShader(gl, vertexShader);
        deleteWebGLShader(gl, fragmentShader);
        return false;
    }

    const program = gl.createProgram();
    if (!program) {
        deleteWebGLShader(gl, vertexShader);
        deleteWebGLShader(gl, fragmentShader);
        return false;
    }

    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    const linkSucceeded = Boolean(gl.getProgramParameter(program, gl.LINK_STATUS));

    deleteWebGLProgram(gl, program);
    deleteWebGLShader(gl, vertexShader);
    deleteWebGLShader(gl, fragmentShader);
    return linkSucceeded;
}

function compileWebGLShader(gl, type, source) {
    const shader = gl.createShader(type);
    if (!shader) {
        return null;
    }
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        gl.deleteShader(shader);
        return null;
    }
    return shader;
}

function deleteWebGLProgram(gl, program) {
    if (!gl || !program || typeof gl.deleteProgram !== "function") {
        return;
    }
    gl.deleteProgram(program);
}

function deleteWebGLShader(gl, shader) {
    if (!gl || !shader || typeof gl.deleteShader !== "function") {
        return;
    }
    gl.deleteShader(shader);
}

function resolveStageLive2DConfig(contextConfig, webLive2DConfig) {
    if (!contextConfig) {
        return webLive2DConfig;
    }
    return {
        ...live2DWebCatalogMatch(webLive2DConfig, contextConfig),
        ...contextConfig,
        available: contextConfig.available !== false,
    };
}

function live2DWebCatalogMatch(webLive2DConfig, contextConfig) {
    const models = webLive2DConfig && Array.isArray(webLive2DConfig.models)
        ? webLive2DConfig.models
        : [];
    const selectionKey = String(contextConfig.selection_key || "");
    const modelUrl = String(contextConfig.model_url || "");
    return models.find((model) => {
        if (!model || typeof model !== "object") {
            return false;
        }
        return (
            (selectionKey && model.selection_key === selectionKey)
            || (modelUrl && model.model_url === modelUrl)
        );
    }) || {};
}

function stageContextLive2DConfig() {
    const contextLive2D = stageContext && typeof stageContext.live2d_model === "object"
        ? stageContext.live2d_model
        : null;
    if (
        !contextLive2D
        || contextLive2D.available === false
        || !contextLive2D.model_url
    ) {
        return null;
    }
    return contextLive2D;
}

function stageContextLive2DKey() {
    const contextConfig = stageContextLive2DConfig();
    if (!contextConfig) {
        return "";
    }
    return String(contextConfig.selection_key || contextConfig.model_url || "");
}

function normalizeLive2DConfig(sourceConfig, source = "web-config") {
    if (!sourceConfig || sourceConfig.available === false) {
        return {
            selection_key: "",
            source,
            model_url: "",
            lip_sync_parameter_ids: DEFAULT_LIP_SYNC_IDS.slice(),
            mouth_form_parameter_id: null,
            expressions: [],
            motions: [],
        };
    }

    const selectedModel = Array.isArray(sourceConfig.models)
        ? sourceConfig.models.find((model) => model && model.model_url)
        : null;
    const modelConfig = selectedModel || sourceConfig;
    if (!modelConfig || modelConfig.available === false) {
        return {
            selection_key: "",
            source,
            model_url: "",
            lip_sync_parameter_ids: DEFAULT_LIP_SYNC_IDS.slice(),
            mouth_form_parameter_id: null,
            expressions: [],
            motions: [],
        };
    }
    const lipSyncParameterIds = Array.isArray(modelConfig.lip_sync_parameter_ids)
        ? modelConfig.lip_sync_parameter_ids.filter((item) => typeof item === "string")
        : [];
    return {
        selection_key: String(modelConfig.selection_key || sourceConfig.selection_key || ""),
        source,
        model_url: String(modelConfig.model_url || ""),
        lip_sync_parameter_ids: lipSyncParameterIds.length > 0
            ? lipSyncParameterIds
            : DEFAULT_LIP_SYNC_IDS.slice(),
        mouth_form_parameter_id: typeof modelConfig.mouth_form_parameter_id === "string"
            ? modelConfig.mouth_form_parameter_id
            : null,
        expressions: normalizeLive2DActionList(modelConfig.expressions),
        motions: normalizeLive2DActionList(modelConfig.motions),
    };
}

function normalizeLive2DActionList(items) {
    return Array.isArray(items)
        ? items
            .filter((item) => item && typeof item === "object")
            .map((item) => ({
                file: String(item.file || ""),
                name: String(item.name || item.file || ""),
                note: String(item.note || ""),
                url: String(item.url || ""),
                group: String(item.group || ""),
                index: Number.isInteger(item.index) ? item.index : 0,
            }))
            .filter((item) => item.file || item.name)
        : [];
}

async function withPixiInitializationGuard(callback) {
    const originalConsoleError = console.error;
    console.error = (...args) => {
        if (isKnownPixiInitializationNoise(args)) {
            return;
        }
        originalConsoleError.apply(console, args);
    };
    try {
        return await callback();
    } finally {
        console.error = originalConsoleError;
    }
}

function isKnownPixiInitializationNoise(args) {
    return args.some((item) => {
        const text = String(
            item && item.message
                ? item.message
                : item,
        );
        return (
            text.includes("PixiJS Error: Could not initialize shader")
            || text.includes("Could not initialize shader")
        );
    });
}

async function createPixiApplication(host) {
    let app;
    if (typeof window.PIXI.Application === "function") {
        app = new window.PIXI.Application({
            resizeTo: host,
            autoStart: true,
            backgroundAlpha: 0,
            antialias: true,
        });
    } else {
        throw new Error("PIXI.Application is unavailable");
    }

    if (typeof app.init === "function") {
        await app.init({
            resizeTo: host,
            autoStart: true,
            backgroundAlpha: 0,
            antialias: true,
        });
    }

    const canvas = app.canvas || app.view;
    if (canvas) {
        host.replaceChildren(canvas);
    }
    return app;
}

function destroyLive2DApp() {
    window.removeEventListener("resize", fitLive2DModel);
    applyMouthValue(0);
    detachStageExpressionHook();
    activeStageExpressionDefinition = null;
    live2dModel = null;
    if (live2dApp && typeof live2dApp.destroy === "function") {
        try {
            live2dApp.destroy(true, {
                children: true,
                texture: true,
                baseTexture: true,
            });
        } catch (_error) {
            // Fallback rendering should keep working even if PIXI cleanup fails.
        }
    }
    live2dApp = null;
}

function fitLive2DModel() {
    if (!live2dModel || !live2dApp || !canvasHost) {
        return;
    }

    const width = Math.max(canvasHost.clientWidth, 1);
    const height = Math.max(canvasHost.clientHeight, 1);
    if (live2dApp.renderer && typeof live2dApp.renderer.resize === "function") {
        live2dApp.renderer.resize(width, height);
    }

    if (live2dModel.anchor && typeof live2dModel.anchor.set === "function") {
        live2dModel.anchor.set(0.5, 0.5);
    }

    const modelWidth = Math.max(live2dModel.width || width, 1);
    const modelHeight = Math.max(live2dModel.height || height, 1);
    const scale = Math.min(width / modelWidth, height / modelHeight) * 0.82;
    if (live2dModel.scale && typeof live2dModel.scale.set === "function") {
        live2dModel.scale.set(Math.max(scale, 0.05));
    }
    live2dModel.x = width * 0.5;
    live2dModel.y = height * 0.62;
}

function markLive2DUnavailable(messageKey) {
    destroyLive2DApp();
    if (canvasHost) {
        canvasHost.dataset.live2d = "fallback";
        canvasHost.dataset.live2dSource = live2dConfig ? live2dConfig.source : "";
        canvasHost.dataset.live2dSelectionKey = live2dConfig ? live2dConfig.selection_key : "";
        canvasHost.dataset.live2dModelUrl = live2dConfig ? live2dConfig.model_url : "";
        canvasHost.dataset.i18nFallbackKey = messageKey;
        canvasHost.textContent = i18n.t(messageKey);
    }
}

function refreshLocalizedStageText() {
    updateSessionLabel();
    renderStageContext();
    if (statusElement) {
        statusElement.textContent = i18n.t(currentStatusKey);
    }
    if (subtitleElement && subtitleIsPlaceholder) {
        subtitleElement.textContent = i18n.t("stage.waiting");
    }
    if (canvasHost && canvasHost.dataset.i18nFallbackKey) {
        canvasHost.textContent = i18n.t(canvasHost.dataset.i18nFallbackKey);
    }
    renderStageTargetOptions(stageTargets);
    updateAudioButtonText();
    updateStageChromeText();
}

function updateAudioButtonText() {
    if (!audioButton) {
        return;
    }
    audioButton.textContent = i18n.t(
        audioUnlocked ? "stage.audio.enabled" : "stage.audio.enable",
    );
}

function updateStageChromeText() {
    if (subtitleToggleButton) {
        subtitleToggleButton.textContent = i18n.t(
            subtitlesHidden ? "stage.subtitle.show" : "stage.subtitle.hide",
        );
    }
    if (menuToggleButton) {
        menuToggleButton.textContent = i18n.t(
            isStageMenuOpen() ? "stage.menu.close" : "stage.menu.open",
        );
    }
}

function readStoredSubtitlesHidden() {
    try {
        return window.localStorage.getItem(STAGE_SUBTITLE_STORAGE_KEY) === "1";
    } catch (_error) {
        return false;
    }
}

function writeStoredSubtitlesHidden(hidden) {
    try {
        window.localStorage.setItem(STAGE_SUBTITLE_STORAGE_KEY, hidden ? "1" : "0");
    } catch (_error) {
        // Subtitle visibility is still applied for this page even if storage is blocked.
    }
}

async function responseToError(response) {
    let detail = `${response.status} ${response.statusText}`;
    try {
        const payload = await response.json();
        if (payload && typeof payload.detail === "string") {
            detail = payload.detail;
        }
    } catch (_error) {
        return new Error(detail);
    }
    return new Error(detail);
}

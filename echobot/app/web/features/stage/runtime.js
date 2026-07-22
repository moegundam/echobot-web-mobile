import {
    fetchStageSessions,
    fetchStageTargets,
} from "./api.js?session-fallback=1";
import {
    fetchSessionRuntimeContext,
    runtimeContextValue,
} from "../../session-runtime-context.js?v=session-runtime-context-1";
import {
    availableSessionNames,
    resolveAvailableSessionName,
} from "../sessions/selection.js?v=session-fallback-1";


const STAGE_CONTEXT_REFRESH_INTERVAL_MS = 60000;


export function createStageRuntimeController({
    elements,
    i18n,
    initialSessionName,
    onStatus,
    onSessionChanged,
    onLive2DChanged,
    getLive2DKey,
}) {
    const {
        stageSurface,
        stageBackgroundImage,
        sessionLabelElement,
        roleLabelElement,
        modelProfileLabelElement,
        voiceProfileLabelElement,
        live2dProfileLabelElement,
        channelLabelElement,
        sessionSelect,
    } = elements;
    let sessionName = String(initialSessionName || "default").trim() || "default";
    let stageTargets = [];
    let stageSessions = [];
    let knownSessionNames = new Set();
    let stageContext = null;
    let stageContextRevision = "";
    let refreshTimerId = 0;
    let contextRequestToken = 0;

    function setStatus(key) {
        onStatus(key);
    }

    function resolveSessionName() {
        return sessionName;
    }

    function getContext() {
        return stageContext;
    }

    function getTargets() {
        return stageTargets.slice();
    }

    function renderStageContext() {
        const context = stageContext && typeof stageContext === "object"
            ? stageContext
            : {};
        applyStageBackgroundFromContext(context);
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

    function applyStageBackgroundFromContext(context = stageContext) {
        if (!stageSurface || !stageBackgroundImage) {
            return;
        }

        const background = stageBackgroundFromContext(context);
        const url = String(background && background.url || "").trim();
        if (!url) {
            stageBackgroundImage.hidden = true;
            stageBackgroundImage.style.backgroundImage = "";
            clearStageBackgroundStyles();
            stageSurface.classList.remove("has-custom-background");
            return;
        }

        const safeUrl = url.replace(/"/g, "%22");
        const transform = normalizeStageBackgroundTransform(background.transform);
        stageBackgroundImage.style.backgroundImage = `url("${safeUrl}")`;
        stageBackgroundImage.hidden = false;
        stageSurface.classList.add("has-custom-background");
        stageSurface.style.setProperty("--stage-background-position-x", `${transform.positionX}%`);
        stageSurface.style.setProperty("--stage-background-position-y", `${transform.positionY}%`);
        stageSurface.style.setProperty("--stage-background-scale-factor", String(transform.scale / 100));
    }

    function stageBackgroundFromContext(context) {
        const stage = context && typeof context.stage === "object" ? context.stage : {};
        return stage && typeof stage.background === "object" ? stage.background : null;
    }

    function normalizeStageBackgroundTransform(transform) {
        const source = transform && typeof transform === "object" ? transform : {};
        return {
            positionX: clampNumber(source.positionX, 0, 100, 50),
            positionY: clampNumber(source.positionY, 0, 100, 50),
            scale: clampNumber(source.scale, 60, 200, 100),
        };
    }

    function clearStageBackgroundStyles() {
        stageSurface.style.removeProperty("--stage-background-position-x");
        stageSurface.style.removeProperty("--stage-background-position-y");
        stageSurface.style.removeProperty("--stage-background-scale-factor");
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

    function renderStageTargetOptions(targets = stageTargets) {
        if (!sessionSelect) {
            return;
        }
        const options = buildStageTargetOptions(
            stageSelectionTargets(targets, stageSessions),
            sessionName,
        );
        sessionSelect.replaceChildren(...options);
        sessionSelect.value = sessionName;
    }

    function stageSelectionTargets(targets, sessions) {
        const selections = Array.isArray(targets) ? [...targets] : [];
        const seenSessions = new Set(
            selections.map((target) => String(target?.session_name || "").trim()),
        );
        for (const session of Array.isArray(sessions) ? sessions : []) {
            const internalSessionName = String(session?.name || "").trim();
            if (!internalSessionName || seenSessions.has(internalSessionName)) {
                continue;
            }
            seenSessions.add(internalSessionName);
            selections.push({
                display_name: internalSessionName,
                enabled: true,
                running: true,
                session_name: internalSessionName,
            });
        }
        return selections;
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

    function updateSessionLabel() {
        if (sessionLabelElement) {
            sessionLabelElement.textContent = i18n.t("stage.sessionLabel", {
                session: sessionName,
            });
        }
    }

    async function loadStageTargets() {
        if (!sessionSelect) {
            return;
        }
        try {
            const [targetPayload, sessionPayload] = await Promise.all([
                fetchStageTargets(),
                fetchStageSessions(),
            ]);
            stageTargets = Array.isArray(targetPayload.targets)
                ? targetPayload.targets
                : [];
            stageSessions = Array.isArray(sessionPayload) ? sessionPayload : [];
            const sessionNames = availableSessionNames(
                stageTargets.map((target) => target?.session_name),
                stageSessions.map((session) => session?.name),
            );
            knownSessionNames = new Set(sessionNames);
            const resolvedSessionName = resolveAvailableSessionName(
                sessionName,
                sessionNames,
            );
            if (resolvedSessionName && resolvedSessionName !== sessionName) {
                sessionName = resolvedSessionName;
                updateSessionLabel();
                onSessionChanged?.(sessionName);
            }
            renderStageTargetOptions(stageTargets);
        } catch (error) {
            console.warn("Unable to load stage targets", error);
            stageTargets = [];
            stageSessions = [];
            knownSessionNames = new Set();
            renderStageTargetOptions([]);
            setStatus("stage.sessionTargetLoadFailed");
        }
    }

    async function loadStageContext() {
        const requestedSessionName = sessionName;
        const requestToken = ++contextRequestToken;
        const previousLive2DKey = getLive2DKey?.() || "";
        if (!knownSessionNames.has(requestedSessionName)) {
            stageContext = null;
            stageContextRevision = "";
            renderStageContext();
            return false;
        }
        try {
            const nextContext = await fetchSessionRuntimeContext(requestedSessionName);
            if (
                requestToken !== contextRequestToken
                || requestedSessionName !== sessionName
            ) {
                return false;
            }
            const nextRevision = String(nextContext?.revision || "").trim();
            if (nextRevision && nextRevision === stageContextRevision) {
                return false;
            }
            stageContext = nextContext;
            stageContextRevision = nextRevision;
        } catch (error) {
            if (
                requestToken !== contextRequestToken
                || requestedSessionName !== sessionName
            ) {
                return false;
            }
            console.warn("Unable to load stage context", error);
            stageContext = null;
            stageContextRevision = "";
            renderStageContext();
            return false;
        }
        renderStageContext();
        const nextLive2DKey = getLive2DKey?.() || "";
        return previousLive2DKey !== nextLive2DKey;
    }

    async function refreshStageContext(options = {}) {
        const expectedRevision = String(options.expectedRevision || "").trim();
        if (expectedRevision && expectedRevision === stageContextRevision) {
            return;
        }
        const live2dChanged = await loadStageContext();
        if (live2dChanged && options.reloadLive2D) {
            await onLive2DChanged?.();
        }
    }

    function startStageContextRefresh() {
        if (refreshTimerId) {
            window.clearInterval(refreshTimerId);
        }
        refreshTimerId = window.setInterval(() => {
            void refreshStageContext({ reloadLive2D: true });
        }, STAGE_CONTEXT_REFRESH_INTERVAL_MS);
        window.addEventListener("pagehide", stopStageContextRefresh, { once: true });
        document.addEventListener("visibilitychange", handleVisibilityChange);
        window.addEventListener("focus", handleWindowFocus);
    }

    function stopStageContextRefresh() {
        if (refreshTimerId) {
            window.clearInterval(refreshTimerId);
            refreshTimerId = 0;
        }
        document.removeEventListener("visibilitychange", handleVisibilityChange);
        window.removeEventListener("focus", handleWindowFocus);
    }

    function handleVisibilityChange() {
        if (!document.hidden) {
            void refreshStageContext({ reloadLive2D: true });
        }
    }

    function handleWindowFocus() {
        void refreshStageContext({ reloadLive2D: true });
    }

    async function setActiveSessionName(value, options = {}) {
        const nextSessionName = String(value || "").trim() || "default";
        sessionName = nextSessionName;
        updateSessionLabel();
        if (sessionSelect && sessionSelect.value !== sessionName) {
            sessionSelect.value = sessionName;
        }
        onSessionChanged?.(sessionName);
        const live2dChanged = await loadStageContext();
        if (live2dChanged) {
            await onLive2DChanged?.();
        }
        if (options.reconnect) {
            onSessionChanged?.(sessionName, { reconnect: true });
        }
    }

    async function init() {
        await loadStageTargets();
        await loadStageContext();
        startStageContextRefresh();
    }

    function refreshLocalizedText() {
        updateSessionLabel();
        renderStageContext();
        renderStageTargetOptions(stageTargets);
    }

    return {
        getContext,
        getTargets,
        getSessionName: resolveSessionName,
        init,
        loadStageContext,
        refreshStageContext,
        refreshLocalizedText,
        renderStageContext,
        renderStageTargetOptions,
        setActiveSessionName,
        startStageContextRefresh,
        stopStageContextRefresh,
    };
}


function clampNumber(value, min, max, fallback) {
    const number = Number.parseFloat(String(value));
    if (!Number.isFinite(number)) {
        return fallback;
    }
    return Math.min(Math.max(number, min), max);
}

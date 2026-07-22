import { normalizeRouteMode } from "../sessions/route-mode.js?v=admin-boundary-1";
import {
    availableSessionNames,
    resolveAvailableSessionName,
} from "../sessions/selection.js?v=session-fallback-1";

export function createMessengerSessionController({
    sessionInput,
    sessionSelect,
    runtimeContextElement,
    i18n,
    requestJson,
    fetchSessionRuntimeContext,
    runtimeContextSummaryItems,
    sessionApiPath = "/api/sessions",
    stageTargetsApiPath = "/api/channels/stage-targets",
    fallbackRouteMode = "chat_only",
    rememberShellSessionName,
    initShellSessionLinks,
    updateSessionUrl,
    setStatus,
    isBusy,
    stopRecording,
    onSessionsChanged,
    onRuntimeContextChanged,
}) {
    let sessions = [];
    let stageTargets = [];
    let knownSessionNames = new Set();
    let runtimeContext = null;
    let runtimeContextRequestToken = 0;

    function selectedSessionName() {
        return String((sessionInput && sessionInput.value) || "default").trim() || "default";
    }

    function currentSessionName() {
        if (sessionSelect && sessionSelect.value) {
            setActiveSessionName(sessionSelect.value);
        }
        return rememberShellSessionName(selectedSessionName());
    }

    function init() {
        const initialSessionName = rememberShellSessionName(resolveInitialSessionName());
        if (sessionInput) {
            sessionInput.value = initialSessionName;
        }
        if (sessionSelect) {
            sessionSelect.addEventListener("change", () => {
                setActiveSessionName(sessionSelect.value, { updateUrl: true });
            });
        }
        void loadSessions();
    }

    async function loadSessions() {
        try {
            const [sessionsResponse, targetsResponse] = await Promise.all([
                requestJson(sessionApiPath),
                requestJson(stageTargetsApiPath).catch((error) => {
                    console.warn("Unable to load messenger channel targets", error);
                    return null;
                }),
            ]);
            sessions = Array.isArray(sessionsResponse) ? sessionsResponse : [];
            stageTargets = targetsResponse && Array.isArray(targetsResponse.targets)
                ? targetsResponse.targets
                : [];
            const sessionNames = availableSessionNames(
                stageTargets.map((target) => target?.session_name),
                sessions.map((session) => session?.name),
            );
            knownSessionNames = new Set(sessionNames);
            onSessionsChanged?.({ sessions, stageTargets });
            const requestedSessionName = selectedSessionName();
            const resolvedSessionName = resolveAvailableSessionName(
                requestedSessionName,
                sessionNames,
            );
            if (resolvedSessionName && sessionInput) {
                sessionInput.value = rememberShellSessionName(resolvedSessionName);
            }
            renderSessionOptions();
            if (resolvedSessionName) {
                setActiveSessionName(resolvedSessionName, {
                    updateUrl: resolvedSessionName !== requestedSessionName,
                });
            } else {
                runtimeContext = null;
                onRuntimeContextChanged?.(runtimeContext);
                renderMessengerRuntimeContext();
            }
        } catch (error) {
            console.warn("Unable to load messenger sessions", error);
            sessions = [];
            stageTargets = [];
            knownSessionNames = new Set();
            onSessionsChanged?.({ sessions, stageTargets });
            renderSessionOptions();
            setStatus("messenger.sessionLoadFailed");
        }
    }

    function renderSessionOptions() {
        if (!sessionSelect) {
            return;
        }
        const currentSession = selectedSessionName();
        sessionSelect.replaceChildren(...buildSessionOptions(sessions, currentSession));
        sessionSelect.value = currentSession;
    }

    function buildSessionOptions(availableSessions, currentSession) {
        const options = [];
        const seenSessions = new Set();
        for (const target of stageTargets) {
            const sessionName = String((target && target.session_name) || "").trim();
            if (!sessionName || seenSessions.has(sessionName)) {
                continue;
            }
            seenSessions.add(sessionName);
            const option = document.createElement("option");
            option.value = sessionName;
            option.textContent = i18n.t("messenger.channelTargetOption", {
                target: String(
                    (target && (target.display_name || target.label)) || sessionName,
                ),
                session: sessionName,
            });
            options.push(option);
        }
        for (const session of availableSessions) {
            const sessionName = String((session && session.name) || "").trim();
            if (!sessionName || seenSessions.has(sessionName)) {
                continue;
            }
            seenSessions.add(sessionName);
            const option = document.createElement("option");
            option.value = sessionName;
            option.textContent = sessionOptionLabel(session);
            options.push(option);
        }
        if (!seenSessions.has(currentSession)) {
            const fallbackOption = document.createElement("option");
            fallbackOption.value = currentSession;
            fallbackOption.textContent = i18n.t("messenger.sessionFallback", {
                session: currentSession,
            });
            options.unshift(fallbackOption);
        }
        return options;
    }

    function setActiveSessionName(value, options = {}) {
        if (isBusy?.()) {
            return selectedSessionName();
        }
        stopRecording?.();
        const nextSessionName = rememberShellSessionName(
            String(value || "").trim() || "default",
        );
        if (sessionInput) {
            sessionInput.value = nextSessionName;
        }
        if (sessionSelect && sessionSelect.value !== nextSessionName) {
            sessionSelect.value = nextSessionName;
        }
        if (options.updateUrl) {
            updateSessionUrl(nextSessionName);
            initShellSessionLinks();
            void loadMessengerRuntimeContext(nextSessionName);
        } else if (runtimeContext?.session_name !== nextSessionName) {
            initShellSessionLinks();
            void loadMessengerRuntimeContext(nextSessionName);
        }
        return nextSessionName;
    }

    async function loadMessengerRuntimeContext(nextSessionName) {
        const requestedSessionName = String(nextSessionName || "default");
        const requestToken = ++runtimeContextRequestToken;
        if (!knownSessionNames.has(requestedSessionName)) {
            runtimeContext = null;
            onRuntimeContextChanged?.(runtimeContext);
            renderMessengerRuntimeContext();
            return;
        }
        try {
            const nextContext = await fetchSessionRuntimeContext(requestedSessionName);
            if (
                requestToken !== runtimeContextRequestToken
                || requestedSessionName !== selectedSessionName()
            ) {
                return;
            }
            runtimeContext = nextContext;
        } catch (error) {
            if (requestToken !== runtimeContextRequestToken) {
                return;
            }
            console.warn("Unable to load messenger runtime context", error);
            runtimeContext = null;
        }
        onRuntimeContextChanged?.(runtimeContext);
        renderMessengerRuntimeContext();
    }

    function renderMessengerRuntimeContext() {
        if (!runtimeContextElement) {
            return;
        }
        if (!runtimeContext) {
            runtimeContextElement.textContent = i18n.t(
                "messenger.runtimeContextUnavailable",
            );
            return;
        }
        const chips = runtimeContextSummaryItems(runtimeContext, i18n.t)
            .map((item) => {
                const chip = document.createElement("span");
                chip.className = "runtime-context-chip";
                const label = document.createElement("strong");
                label.textContent = item.label;
                const value = document.createElement("span");
                value.textContent = item.value;
                chip.append(label, value);
                return chip;
            });
        runtimeContextElement.replaceChildren(...chips);
    }

    function activeRouteMode(sessionName) {
        const contextSession = String(runtimeContext?.session_name || "").trim();
        const contextRouteMode = String(runtimeContext?.route_mode || "").trim();
        if (contextSession === sessionName && contextRouteMode) {
            return normalizeRouteMode(contextRouteMode);
        }
        const session = sessions.find((item) => {
            return String((item && item.name) || "").trim() === sessionName;
        });
        return normalizeRouteMode(session?.route_mode || fallbackRouteMode);
    }

    function refresh() {
        renderSessionOptions();
        renderMessengerRuntimeContext();
    }

    return {
        activeRouteMode,
        currentSessionName,
        init,
        loadMessengerRuntimeContext,
        loadSessions,
        refresh,
        renderMessengerRuntimeContext,
        selectedSessionName,
        setActiveSessionName,
    };
}

function resolveInitialSessionName() {
    const params = new URLSearchParams(window.location.search);
    return String(params.get("session_name") || "default").trim() || "default";
}

function sessionOptionLabel(session) {
    const sessionName = String((session && session.name) || "").trim();
    const roleName = String((session && session.role_name) || "").trim();
    const channel = String(
        (session && (session.channel_integration_id || session.channel_type)) || "",
    ).trim();
    const details = [
        roleName && roleName !== "default" ? roleName : "",
        channel,
    ].filter(Boolean);
    return details.length > 0
        ? `${sessionName} · ${details.join(" · ")}`
        : sessionName;
}

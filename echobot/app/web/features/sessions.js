import {
    DEFAULT_SESSION_NAME,
    appState,
    SESSION_SYNC_POLL_INTERVAL_MS,
    audioState,
    chatState,
    roleState,
    sessionState,
} from "../core/store.js";
import { DOM } from "../core/dom.js";
import { createSessionsApi } from "./sessions/api.js?v=admin-boundary-1";
import {
    buildSpokenText,
    findAppendedMessages,
    normalizeHistory,
    renderSessionHistory,
    shouldAnnounceNewMessages,
} from "./sessions/history.js?v=admin-boundary-1";
import { normalizeRouteMode, routeModeLabel } from "./sessions/route-mode.js?v=admin-boundary-1";
import { createSessionSidebarController } from "./sessions/sidebar.js?v=admin-boundary-1";

export function createSessionsModule(deps) {
    const {
        addMessage,
        addSystemMessage,
        clearMessages,
        formatTimestamp,
        normalizeSessionName,
        requestJson,
        speakText,
        setRunStatus,
        stopSpeechPlayback,
        t = (key) => key,
    } = deps;

    const api = createSessionsApi({
        requestJson: requestJson,
    });
    const sidebar = createSessionSidebarController({
        formatTimestamp: formatTimestamp,
        t: t,
    });

    let roleHooks = {
        syncRolePanelForCurrentSession() {
            return Promise.resolve();
        },
    };

    function bindRoleHooks(hooks) {
        roleHooks = {
            ...roleHooks,
            ...(hooks || {}),
        };
    }

    async function initializeSessionPanel(defaultSessionName) {
        sidebar.setSessionControlsBusy(true, t("console.loadingSessions"));

        try {
            await loadStageTargets();
            const sessionSummaries = await api.requestSessionSummaries();
            sidebar.applySessionSummaries(sessionSummaries);

            const initialSessionName = resolveInitialSessionName(defaultSessionName, sessionSummaries);
            const sessionDetail = initialSessionName === defaultSessionName
                ? await requestJson("/api/sessions/current")
                : await api.switchCurrentSession(initialSessionName);

            applySessionDetail(sessionDetail);
            renderSessionSettings();
            sidebar.setSessionSidebarStatus("");
            startSessionSyncPolling();
        } finally {
            sidebar.setSessionControlsBusy(false);
        }
    }

    async function loadStageTargets() {
        try {
            const payload = await requestJson("/api/channels/stage-targets");
            sessionState.stageTargets = Array.isArray(payload.targets)
                ? payload.targets
                : [];
        } catch (error) {
            console.warn("Unable to load stage targets for session settings", error);
            sessionState.stageTargets = [];
        }
        renderSessionSettings();
    }

    function resolveInitialSessionName(defaultSessionName, sessionSummaries) {
        const storedSessionName = String(window.localStorage.getItem("echobot.web.session") || "").trim();
        const candidateNames = new Set((sessionSummaries || []).map((item) => item.name));

        if (storedSessionName && candidateNames.has(storedSessionName)) {
            return storedSessionName;
        }
        if (defaultSessionName && candidateNames.has(defaultSessionName)) {
            return defaultSessionName;
        }
        if (sessionSummaries && sessionSummaries.length > 0) {
            return sessionSummaries[0].name;
        }
        return defaultSessionName || DEFAULT_SESSION_NAME;
    }

    async function refreshSessionList() {
        if (sessionState.sessionLoading) {
            return;
        }

        sidebar.setSessionControlsBusy(true, t("console.loadingSessions"));
        try {
            const sessionSummaries = await api.requestSessionSummaries();
            sidebar.applySessionSummaries(sessionSummaries);
            sidebar.setSessionSidebarStatus("");
        } catch (error) {
            console.error(error);
            sidebar.setSessionSidebarStatus(error.message || t("console.sessionListLoadFailed"));
            addMessage("system", `${t("console.sessionListLoadFailed")}: ${error.message || error}`, t("console.systemLabel"));
        } finally {
            sidebar.setSessionControlsBusy(false);
        }
    }

    function startSessionSyncPolling() {
        if (sessionState.sessionSyncPollTimerId) {
            return;
        }

        sessionState.sessionSyncPollTimerId = window.setInterval(() => {
            void syncCurrentSessionFromServer({
                announceNewMessages: true,
                refreshSummaries: true,
            });
        }, SESSION_SYNC_POLL_INTERVAL_MS);
    }

    async function syncCurrentSessionFromServer(options = {}) {
        if (
            sessionState.sessionSyncInFlight
            || sessionState.sessionLoading
            || (
                !options.force
                && (chatState.chatBusy || chatState.activeChatJobId)
            )
        ) {
            return;
        }

        const sessionName = normalizeSessionName(
            options.sessionName || sessionState.currentSessionName || DEFAULT_SESSION_NAME,
        );
        sessionState.sessionSyncInFlight = true;
        try {
            const sessionDetail = await api.requestSessionDetail(sessionName);
            if (
                !options.force
                && sessionDetail.updated_at === sessionState.currentSessionUpdatedAt
            ) {
                return;
            }
            applySessionDetail(sessionDetail, {
                announceNewMessages: Boolean(options.announceNewMessages),
            });
            if (Boolean(options.refreshSummaries)) {
                sidebar.applySessionSummaries(await api.requestSessionSummaries());
            }
        } catch (error) {
            console.error("Failed to sync session detail", error);
        } finally {
            sessionState.sessionSyncInFlight = false;
        }
    }

    async function handleSessionListClick(event) {
        const actionButton = event.target.closest("[data-session-action]");
        if (!actionButton || !DOM.sessionList || !DOM.sessionList.contains(actionButton)) {
            return;
        }

        const action = actionButton.dataset.sessionAction || "";
        const sessionName = actionButton.dataset.sessionName || "";
        if (!sessionName) {
            return;
        }

        if (action === "switch") {
            await switchSession(sessionName);
        }
    }

    async function switchSession(sessionName) {
        if (
            chatState.chatBusy
            || sessionState.sessionLoading
            || !sessionName
            || sessionName === sessionState.currentSessionName
        ) {
            return;
        }

        stopSpeechPlayback();
        sidebar.setSessionControlsBusy(true, t("console.switchingSession"));

        try {
            const sessionDetail = await api.switchCurrentSession(sessionName);
            applySessionDetail(sessionDetail);
            sidebar.setSessionSidebarStatus("");
            setRunStatus(t("console.sessionSwitched", { session: sessionDetail.name }));
        } catch (error) {
            console.error(error);
            sidebar.setSessionSidebarStatus(error.message || t("console.sessionSwitchFailed"));
            addMessage("system", `${t("console.sessionSwitchFailed")}: ${error.message || error}`, t("console.systemLabel"));
        } finally {
            sidebar.setSessionControlsBusy(false);
        }
    }

    function applySessionDetail(sessionDetail, options = {}) {
        const sessionName = normalizeSessionName(sessionDetail.name || DEFAULT_SESSION_NAME);
        const nextHistory = normalizeHistory(sessionDetail.history);
        const appendedMessages = shouldAnnounceNewMessages(
            options,
            sessionName,
            sessionState.currentSessionName,
            sessionState.currentSessionHistory,
        )
            ? findAppendedMessages(sessionState.currentSessionHistory, nextHistory)
            : [];

        sessionState.currentSessionName = sessionName;
        sessionState.currentSessionUpdatedAt = String(sessionDetail.updated_at || "").trim();
        sessionState.currentSessionHistory = nextHistory;
        roleState.currentRoleName = sessionDetail.role_name || "default";
        sessionState.currentRouteMode = normalizeRouteMode(sessionDetail.route_mode);

        DOM.sessionLabel.textContent = t("console.sessionLabel", { session: sessionName });
        window.localStorage.setItem("echobot.web.session", sessionName);
        sidebar.syncRouteModeSelect();
        renderSessionSettings();

        renderSessionHistory(nextHistory, {
            addMessage: addMessage,
            addSystemMessage: addSystemMessage,
            clearMessages: clearMessages,
            t: t,
        });
        sidebar.renderSessionList(sessionState.sessions);
        sidebar.updateSessionSidebarSummary();
        void roleHooks.syncRolePanelForCurrentSession();
        if (appendedMessages.length > 0) {
            void handleAppendedMessages(appendedMessages);
        }
    }

    function renderSessionSettings() {
        const sessionName = sessionState.currentSessionName || DEFAULT_SESSION_NAME;
        const roleName = roleState.currentRoleName || "default";
        const routeMode = normalizeRouteMode(sessionState.currentRouteMode);
        const sourceLabel = sessionSourceLabel(sessionName);
        const modelLabel = sessionModelProfileLabel(roleName);
        const updatedLabel = formatTimestamp(sessionState.currentSessionUpdatedAt)
            || t("console.noUpdatedTime");

        setText(sessionSettingsElement("current"), sessionName);
        setText(sessionSettingsElement("source"), sourceLabel);
        setText(sessionSettingsElement("role"), roleName);
        setText(sessionSettingsElement("model"), modelLabel);
        setText(sessionSettingsElement("route"), routeModeLabel(routeMode, t));
        setText(sessionSettingsElement("updated"), updatedLabel);
        updateSessionLink(DOM.consoleNavStageLink, "/stage", sessionName);
        updateSessionLink(DOM.consoleNavMessengerLink, "/messenger", sessionName);
        updateSessionLink(sessionSettingsElement("stage-link"), "/stage", sessionName);
        updateSessionLink(sessionSettingsElement("messenger-link"), "/messenger", sessionName);
    }

    function sessionSettingsElement(key) {
        return document.getElementById(`session-settings-${key}`);
    }

    function sessionSourceLabel(sessionName) {
        const target = findStageTarget(sessionName);
        if (!target) {
            return t("console.sessionSourceManual");
        }
        const label = String(
            target.display_name || target.label || target.channel || "",
        ).trim();
        return label || t("console.sessionSourceManual");
    }

    function findStageTarget(sessionName) {
        const normalizedSessionName = String(sessionName || "").trim();
        return (sessionState.stageTargets || []).find((target) => (
            target
            && String(target.session_name || "").trim() === normalizedSessionName
        )) || null;
    }

    function sessionModelProfileLabel(roleName) {
        const modelProfiles = appState.config && appState.config.model_profiles
            ? appState.config.model_profiles
            : {};
        const roleBindings = modelProfiles && typeof modelProfiles.role_bindings === "object"
            ? modelProfiles.role_bindings
            : {};
        const profileId = String(
            roleBindings[roleName] || modelProfiles.active_profile_id || "",
        ).trim();
        if (!profileId) {
            return "-";
        }
        const profiles = Array.isArray(modelProfiles.profiles)
            ? modelProfiles.profiles
            : [];
        const profile = profiles.find((item) => (
            item && String(item.profile_id || "") === profileId
        ));
        return String((profile && profile.label) || profileId);
    }

    function updateSessionLink(linkElement, pathname, sessionName) {
        if (!linkElement) {
            return;
        }
        const url = new URL(pathname, window.location.origin);
        url.searchParams.set("session_name", sessionName || DEFAULT_SESSION_NAME);
        linkElement.href = `${url.pathname}${url.search}`;
    }

    function setText(element, text) {
        if (element) {
            element.textContent = String(text || "").trim() || "-";
        }
    }

    async function handleAppendedMessages(messages) {
        const spokenText = buildSpokenText(messages);
        if (!spokenText) {
            return;
        }

        setRunStatus(t("console.newSessionMessage"));
        if (!audioState.ttsEnabled) {
            return;
        }

        try {
            await speakText(spokenText);
        } catch (error) {
            console.error("Failed to speak synced session messages", error);
        }
    }

    async function handleRouteModeChange() {
        if (
            !DOM.routeModeSelect
            || chatState.chatBusy
            || sessionState.sessionLoading
            || chatState.activeChatJobId
        ) {
            sidebar.syncRouteModeSelect();
            return;
        }

        const nextRouteMode = normalizeRouteMode(DOM.routeModeSelect.value);
        const currentRouteMode = normalizeRouteMode(sessionState.currentRouteMode);
        if (nextRouteMode === currentRouteMode) {
            sidebar.syncRouteModeSelect();
            return;
        }

        const sessionName = normalizeSessionName(
            sessionState.currentSessionName || DEFAULT_SESSION_NAME,
        );
        DOM.routeModeSelect.disabled = true;
        setRunStatus(t("console.switchingRouteMode"));

        try {
            const sessionDetail = await api.updateSessionRouteMode(
                sessionName,
                nextRouteMode,
            );
            applySessionDetail(sessionDetail);
            setRunStatus(t("console.routeModeSwitched", {
                mode: routeModeLabel(nextRouteMode, t),
            }));
        } catch (error) {
            console.error(error);
            sidebar.syncRouteModeSelect();
            addMessage("system", `${t("console.routeModeSwitchFailed")}: ${error.message || error}`, t("console.systemLabel"));
            setRunStatus(error.message || t("console.routeModeSwitchFailed"));
        } finally {
            DOM.routeModeSelect.disabled = (
                chatState.chatBusy
                || sessionState.sessionLoading
                || Boolean(chatState.activeChatJobId)
            );
        }
    }

    return {
        applySessionDetail: applySessionDetail,
        applySessionSummaries: sidebar.applySessionSummaries,
        bindRoleHooks: bindRoleHooks,
        handleRouteModeChange: handleRouteModeChange,
        handleSessionListClick: handleSessionListClick,
        initializeSessionPanel: initializeSessionPanel,
        refreshSessionList: refreshSessionList,
        renderSessionList: sidebar.renderSessionList,
        refreshSessionSettings: renderSessionSettings,
        refreshLocalizedText() {
            const sessionName = sessionState.currentSessionName || DEFAULT_SESSION_NAME;
            if (DOM.sessionLabel) {
                DOM.sessionLabel.textContent = t("console.sessionLabel", { session: sessionName });
            }
            renderSessionSettings();
            sidebar.refreshLocalizedText();
        },
        requestSessionDetail: api.requestSessionDetail,
        requestSessionSummaries: api.requestSessionSummaries,
        syncCurrentSessionFromServer: syncCurrentSessionFromServer,
    };
}

import { DOM } from "../../core/dom.js";
import { chatState, sessionState } from "../../core/store.js";
import { normalizeRouteMode } from "./route-mode.js";

export function createSessionSidebarController(deps) {
    const { formatTimestamp } = deps;
    const t = typeof deps.t === "function" ? deps.t : (key, params = {}) => {
        return String(key).replace(/\{([A-Za-z0-9_]+)\}/g, (_match, name) => {
            return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : "";
        });
    };

    function applySessionSummaries(sessionSummaries) {
        sessionState.sessions = Array.isArray(sessionSummaries) ? sessionSummaries : [];
        renderSessionList(sessionState.sessions);
        updateSessionSidebarSummary();
    }

    function syncRouteModeSelect() {
        if (!DOM.routeModeSelect) {
            return;
        }
        DOM.routeModeSelect.value = normalizeRouteMode(sessionState.currentRouteMode);
    }

    function setSessionControlsBusy(isBusy, statusText = null) {
        sessionState.sessionLoading = isBusy;

        if (DOM.sessionCreateButton) {
            DOM.sessionCreateButton.disabled = isBusy || chatState.chatBusy;
        }
        if (DOM.sessionRefreshButton) {
            DOM.sessionRefreshButton.disabled = isBusy || chatState.chatBusy;
        }
        if (DOM.sessionSidebarClose) {
            DOM.sessionSidebarClose.disabled = isBusy;
        }
        if (DOM.routeModeSelect) {
            DOM.routeModeSelect.disabled = (
                isBusy
                || chatState.chatBusy
                || Boolean(chatState.activeChatJobId)
            );
        }

        renderSessionList(sessionState.sessions);
        if (typeof statusText === "string") {
            setSessionSidebarStatus(statusText);
        }
    }

    function setSessionSidebarStatus(text) {
        if (!DOM.sessionSidebarStatus) {
            return;
        }
        DOM.sessionSidebarStatus.textContent = String(text || "").trim();
    }

    function updateSessionSidebarSummary() {
        if (!DOM.sessionSidebarSummary) {
            return;
        }

        if (!sessionState.sessions || sessionState.sessions.length === 0) {
            DOM.sessionSidebarSummary.textContent = t("console.noSessions");
            return;
        }

        const currentSessionName = sessionState.currentSessionName || sessionState.sessions[0].name;
        DOM.sessionSidebarSummary.textContent = t("console.sessionSummary", {
            count: sessionState.sessions.length,
            session: currentSessionName,
        });
    }

    function renderSessionList(sessionSummaries) {
        if (!DOM.sessionList) {
            return;
        }

        DOM.sessionList.innerHTML = "";
        if (!sessionSummaries || sessionSummaries.length === 0) {
            const empty = document.createElement("p");
            empty.className = "session-empty";
            empty.textContent = t("console.sessionEmpty");
            DOM.sessionList.appendChild(empty);
            return;
        }

        sessionSummaries.forEach((sessionSummary) => {
            DOM.sessionList.appendChild(buildSessionCard(sessionSummary));
        });
    }

    function buildSessionCard(sessionSummary) {
        const isActive = sessionSummary.name === sessionState.currentSessionName;
        const container = document.createElement("article");
        container.className = isActive ? "session-card session-card-active" : "session-card";

        const mainButton = document.createElement("button");
        mainButton.type = "button";
        mainButton.className = "session-card-main";
        mainButton.dataset.sessionAction = "switch";
        mainButton.dataset.sessionName = sessionSummary.name;
        mainButton.disabled = chatState.chatBusy || sessionState.sessionLoading || isActive;

        const header = document.createElement("div");
        header.className = "session-card-header";

        const title = document.createElement("p");
        title.className = "session-card-title";
        title.textContent = sessionSummary.name;

        const count = document.createElement("span");
        count.className = "session-card-count";
        count.textContent = t("console.messageCount", {
            count: sessionSummary.message_count || 0,
        });

        header.appendChild(title);
        header.appendChild(count);
        mainButton.appendChild(header);

        const meta = document.createElement("div");
        meta.className = "session-card-meta";
        meta.textContent = formatTimestamp(sessionSummary.updated_at) || t("console.noUpdatedTime");
        mainButton.appendChild(meta);

        container.appendChild(mainButton);
        return container;
    }

    return {
        applySessionSummaries: applySessionSummaries,
        renderSessionList: renderSessionList,
        refreshLocalizedText() {
            updateSessionSidebarSummary();
            renderSessionList(sessionState.sessions);
        },
        setSessionControlsBusy: setSessionControlsBusy,
        setSessionSidebarStatus: setSessionSidebarStatus,
        syncRouteModeSelect: syncRouteModeSelect,
        updateSessionSidebarSummary: updateSessionSidebarSummary,
    };
}

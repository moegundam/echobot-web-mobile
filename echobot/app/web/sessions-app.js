import { initShellI18n } from "./shell-i18n.js?v=admin-sessions-1";
import { initShellDisplayMode } from "./shell-display-mode.js?v=admin-sessions-1";
import {
    initShellSessionLinks,
    rememberShellSessionName,
} from "./shell-session-links.js?v=admin-sessions-1";

const state = {
    sessions: [],
    busy: false,
    loaded: false,
    statusKey: "sessions.loading",
    statusParams: {},
    statusRaw: "",
};

const DOM = {
    create: document.getElementById("sessions-create"),
    list: document.getElementById("sessions-list"),
    refresh: document.getElementById("sessions-refresh"),
    status: document.getElementById("sessions-status"),
};

const i18n = initShellI18n({
    onChange: () => {
        displayMode.refresh();
        render();
        refreshStatus();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
initShellSessionLinks();

DOM.create?.addEventListener("click", () => {
    void createSession();
});
DOM.refresh?.addEventListener("click", () => {
    void loadSessions();
});
DOM.list?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-session-action]");
    if (!button) {
        return;
    }
    const action = String(button.dataset.sessionAction || "");
    const sessionName = String(button.dataset.sessionName || "");
    if (action === "console") {
        void useInConsole(sessionName);
    } else if (action === "rename") {
        void renameSession(sessionName);
    } else if (action === "delete") {
        void deleteSession(sessionName);
    }
});

void loadSessions();

async function loadSessions() {
    setBusy(true);
    state.loaded = false;
    setStatusKey("sessions.loading");
    try {
        const sessions = await requestJson("/api/sessions");
        state.sessions = Array.isArray(sessions) ? sessions : [];
        state.loaded = true;
        render();
        setStatusKey("sessions.ready", { count: state.sessions.length });
    } catch (error) {
        console.error(error);
        state.loaded = false;
        state.sessions = [];
        render();
        setRawStatus(i18n.t("sessions.loadFailed", {
            message: error.message || String(error),
        }));
    } finally {
        setBusy(false);
    }
}

function render() {
    if (!DOM.list) {
        return;
    }
    DOM.list.innerHTML = "";
    if (!state.sessions.length) {
        const empty = document.createElement("p");
        empty.className = "session-admin-empty";
        empty.textContent = i18n.t("sessions.empty");
        DOM.list.appendChild(empty);
        return;
    }
    state.sessions.forEach((session) => {
        DOM.list.appendChild(buildSessionCard(session));
    });
}

function buildSessionCard(session) {
    const sessionName = String(session.name || "default");
    const card = document.createElement("article");
    card.className = "session-admin-card";

    const header = document.createElement("div");
    header.className = "session-admin-card-header";

    const title = document.createElement("h3");
    title.textContent = sessionName;
    header.appendChild(title);

    const count = document.createElement("span");
    count.textContent = i18n.t("sessions.messageCount", {
        count: session.message_count || 0,
    });
    header.appendChild(count);
    card.appendChild(header);

    const meta = document.createElement("p");
    meta.className = "session-admin-meta";
    meta.textContent = i18n.t("sessions.updatedAt", {
        value: formatTimestamp(session.updated_at) || "-",
    });
    card.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "session-admin-card-actions";
    actions.appendChild(buildActionButton("sessions.useInConsole", "console", sessionName));
    actions.appendChild(buildSessionLink("sessions.openStage", `/stage?session_name=${encodeURIComponent(sessionName)}`));
    actions.appendChild(buildSessionLink("sessions.openMessenger", `/messenger?session_name=${encodeURIComponent(sessionName)}`));
    actions.appendChild(buildActionButton("sessions.rename", "rename", sessionName));
    actions.appendChild(buildActionButton("sessions.delete", "delete", sessionName, { danger: true }));
    card.appendChild(actions);

    return card;
}

function buildActionButton(labelKey, action, sessionName, options = {}) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.sessionAction = action;
    button.dataset.sessionName = sessionName;
    button.disabled = state.busy;
    button.textContent = i18n.t(labelKey);
    if (options.danger) {
        button.className = "session-admin-danger";
    }
    return button;
}

function buildSessionLink(labelKey, href) {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = i18n.t(labelKey);
    return link;
}

async function createSession() {
    if (state.busy) {
        return;
    }
    const rawName = window.prompt(i18n.t("sessions.createPrompt"));
    const nextName = String(rawName || "").trim();
    if (!nextName) {
        return;
    }
    setBusy(true);
    setStatusKey("sessions.creating");
    try {
        await requestJson("/api/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: nextName }),
        });
        rememberShellSessionName(nextName);
        await loadSessions();
        setStatusKey("sessions.created", { session: nextName });
    } catch (error) {
        console.error(error);
        setRawStatus(i18n.t("sessions.createFailed", {
            message: error.message || String(error),
        }));
    } finally {
        setBusy(false);
    }
}

async function useInConsole(sessionName) {
    const normalizedName = String(sessionName || "").trim();
    if (!normalizedName || state.busy) {
        return;
    }
    setBusy(true);
    setStatusKey("sessions.usingInConsole");
    try {
        await requestJson("/api/sessions/current", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: normalizedName }),
        });
        rememberShellSessionName(normalizedName);
        window.location.href = "/console";
    } catch (error) {
        console.error(error);
        setRawStatus(i18n.t("sessions.useInConsoleFailed", {
            message: error.message || String(error),
        }));
        setBusy(false);
    }
}

async function renameSession(sessionName) {
    const currentName = String(sessionName || "").trim();
    if (!currentName || state.busy) {
        return;
    }
    const rawName = window.prompt(i18n.t("sessions.renamePrompt"), currentName);
    const nextName = String(rawName || "").trim();
    if (!nextName || nextName === currentName) {
        return;
    }
    setBusy(true);
    setStatusKey("sessions.renaming");
    try {
        await requestJson(`/api/sessions/${encodeURIComponent(currentName)}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: nextName }),
        });
        rememberShellSessionName(nextName);
        await loadSessions();
        setStatusKey("sessions.renamed", { session: nextName });
    } catch (error) {
        console.error(error);
        setRawStatus(i18n.t("sessions.renameFailed", {
            message: error.message || String(error),
        }));
    } finally {
        setBusy(false);
    }
}

async function deleteSession(sessionName) {
    const normalizedName = String(sessionName || "").trim();
    if (!normalizedName || state.busy) {
        return;
    }
    if (!window.confirm(i18n.t("sessions.deleteConfirm", { session: normalizedName }))) {
        return;
    }
    setBusy(true);
    setStatusKey("sessions.deleting");
    try {
        await requestJson(`/api/sessions/${encodeURIComponent(normalizedName)}`, {
            method: "DELETE",
        });
        await loadSessions();
        setStatusKey("sessions.deleted", { session: normalizedName });
    } catch (error) {
        console.error(error);
        setRawStatus(i18n.t("sessions.deleteFailed", {
            message: error.message || String(error),
        }));
    } finally {
        setBusy(false);
    }
}

function setBusy(isBusy) {
    state.busy = isBusy;
    [DOM.create, DOM.refresh].forEach((button) => {
        if (button) {
            button.disabled = isBusy;
        }
    });
    DOM.list?.querySelectorAll("button").forEach((button) => {
        button.disabled = isBusy;
    });
}

function setStatusKey(key, params = {}) {
    state.statusKey = key;
    state.statusParams = params;
    state.statusRaw = "";
    refreshStatus();
}

function setRawStatus(text) {
    state.statusRaw = String(text || "").trim();
    refreshStatus();
}

function refreshStatus() {
    if (!DOM.status) {
        return;
    }
    DOM.status.textContent = state.statusRaw || i18n.t(state.statusKey, state.statusParams);
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        headers: { Accept: "application/json", ...(options.headers || {}) },
        ...options,
    });
    if (!response.ok) {
        throw await responseToError(response);
    }
    if (response.status === 204) {
        return null;
    }
    return response.json();
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

function formatTimestamp(value) {
    if (!value) {
        return "";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return String(value);
    }
    return new Intl.DateTimeFormat(i18n.language || "en", {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(date);
}

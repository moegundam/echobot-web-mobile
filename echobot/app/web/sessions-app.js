import { initShellI18n } from "./shell-i18n.js?v=admin-sessions-1";
import { initShellDisplayMode } from "./shell-display-mode.js?v=admin-sessions-1";
import {
    initShellSessionLinks,
    rememberShellSessionName,
} from "./shell-session-links.js?v=admin-sessions-1";

const state = {
    sessions: [],
    characters: [],
    channelIntegrations: [],
    editingSessionName: "",
    busy: false,
    loaded: false,
    statusKey: "sessions.loading",
    statusParams: {},
    statusRaw: "",
};

const DOM = {
    createForm: document.getElementById("sessions-create-form"),
    create: document.getElementById("sessions-create"),
    createName: document.getElementById("sessions-create-name"),
    createCharacter: document.getElementById("sessions-create-character"),
    createRouteMode: document.getElementById("sessions-create-route-mode"),
    createChannelType: document.getElementById("sessions-create-channel-type"),
    createChannelIntegration: document.getElementById("sessions-create-channel-integration"),
    editForm: document.getElementById("sessions-edit-form"),
    editTitle: document.getElementById("sessions-edit-title"),
    editCharacter: document.getElementById("sessions-edit-character"),
    editRouteMode: document.getElementById("sessions-edit-route-mode"),
    editChannelType: document.getElementById("sessions-edit-channel-type"),
    editChannelIntegration: document.getElementById("sessions-edit-channel-integration"),
    editSave: document.getElementById("sessions-edit-save"),
    editCancel: document.getElementById("sessions-edit-cancel"),
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

DOM.createForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void createSession();
});
DOM.createChannelIntegration?.addEventListener("change", () => {
    syncChannelTypeFromIntegration(DOM.createChannelIntegration, DOM.createChannelType);
});
DOM.editForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveSessionBinding();
});
DOM.editChannelIntegration?.addEventListener("change", () => {
    syncChannelTypeFromIntegration(DOM.editChannelIntegration, DOM.editChannelType);
});
DOM.editCancel?.addEventListener("click", () => {
    clearEditForm();
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
    } else if (action === "edit") {
        void editSession(sessionName);
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
        const [sessions, characters, channelIntegrations] = await Promise.all([
            requestJson("/api/sessions"),
            requestJson("/api/character-profiles").catch((error) => {
                console.warn("Unable to load characters for session creation", error);
                return { characters: [] };
            }),
            requestJson("/api/channel-integrations").catch((error) => {
                console.warn("Unable to load channel integrations for session creation", error);
                return { integrations: [] };
            }),
        ]);
        state.sessions = Array.isArray(sessions) ? sessions : [];
        state.characters = Array.isArray(characters.characters)
            ? characters.characters
            : [];
        state.channelIntegrations = Array.isArray(channelIntegrations.integrations)
            ? channelIntegrations.integrations
            : [];
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
    renderCreateOptions();
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

function renderCreateOptions() {
    renderCharacterOptions(DOM.createCharacter);
    renderCharacterOptions(DOM.editCharacter);
    renderChannelTypeOptions(DOM.createChannelType);
    renderChannelTypeOptions(DOM.editChannelType);
    renderChannelIntegrationOptions(DOM.createChannelIntegration);
    renderChannelIntegrationOptions(DOM.editChannelIntegration);
}

function renderCharacterOptions(select) {
    if (!select) {
        return;
    }
    const selectedValue = select.value;
    select.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t("sessions.useDefaultCharacter");
    select.appendChild(emptyOption);
    state.characters.forEach((character) => {
        const option = document.createElement("option");
        option.value = String(character.name || "");
        option.textContent = String(character.name || "");
        select.appendChild(option);
    });
    select.value = selectedValue;
}

function renderChannelTypeOptions(select) {
    if (!select) {
        return;
    }
    const selectedValue = select.value;
    select.replaceChildren();
    const options = [
        ["", i18n.t("sessions.noChannelBinding")],
        ["web", "Web"],
        ["telegram", "Telegram"],
        ["discord", "Discord"],
        ["line", "LINE"],
        ["whatsapp", "WhatsApp"],
        ["qq", "QQ"],
    ];
    const existingTypes = new Set(options.map(([value]) => value));
    state.channelIntegrations.forEach((integration) => {
        const type = String(integration.type || integration.id || "").trim();
        if (!type || existingTypes.has(type)) {
            return;
        }
        existingTypes.add(type);
        options.push([type, channelLabel(integration)]);
    });
    options.forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
    });
    select.value = selectedValue;
}

function renderChannelIntegrationOptions(select) {
    if (!select) {
        return;
    }
    const selectedValue = select.value;
    select.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t("sessions.noChannelIntegration");
    select.appendChild(emptyOption);
    state.channelIntegrations.forEach((integration) => {
        const option = document.createElement("option");
        option.value = String(integration.id || "");
        option.textContent = channelLabel(integration);
        select.appendChild(option);
    });
    select.value = selectedValue;
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
    actions.appendChild(buildActionButton("sessions.edit", "edit", sessionName));
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
    const nextName = String((DOM.createName && DOM.createName.value) || "").trim();
    if (!nextName) {
        setStatusKey("sessions.nameRequired");
        return;
    }
    const roleName = String((DOM.createCharacter && DOM.createCharacter.value) || "").trim();
    const routeMode = normalizeRouteMode(
        (DOM.createRouteMode && DOM.createRouteMode.value) || "",
    );
    const channelType = String((DOM.createChannelType && DOM.createChannelType.value) || "").trim();
    const channelIntegrationId = String(
        (DOM.createChannelIntegration && DOM.createChannelIntegration.value) || "",
    ).trim();
    setBusy(true);
    setStatusKey("sessions.creating");
    try {
        await requestJson("/api/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: nextName,
                role_name: roleName || undefined,
                route_mode: routeMode || undefined,
                channel_type: channelType || undefined,
                channel_integration_id: channelIntegrationId || undefined,
            }),
        });
        rememberShellSessionName(nextName);
        if (DOM.createName) {
            DOM.createName.value = "";
        }
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

function syncChannelTypeFromIntegration(integrationSelect, channelTypeSelect) {
    const integrationId = String(
        (integrationSelect && integrationSelect.value) || "",
    ).trim();
    const integration = state.channelIntegrations
        .find((item) => String(item.id || "") === integrationId);
    if (!integration) {
        return;
    }
    const type = String(integration.type || integration.id || "").trim();
    if (type && channelTypeSelect) {
        channelTypeSelect.value = type;
    }
}

function channelLabel(integration) {
    const name = String(integration && integration.name || integration && integration.id || "");
    if (integration && integration.enabled === false) {
        return `${name} · ${i18n.t("channelTargets.disabled")}`;
    }
    if (integration && integration.running === false) {
        return `${name} · ${i18n.t("channelTargets.notRunning")}`;
    }
    return name;
}

function normalizeRouteMode(routeMode) {
    const value = String(routeMode || "").trim().toLowerCase();
    if (value === "agent") {
        return "force_agent";
    }
    return ["chat_only", "auto", "force_agent"].includes(value) ? value : "chat_only";
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

async function editSession(sessionName) {
    const normalizedName = String(sessionName || "").trim();
    if (!normalizedName || state.busy) {
        return;
    }
    setBusy(true);
    setStatusKey("sessions.loadingBinding", { session: normalizedName });
    try {
        const detail = await requestJson(`/api/sessions/${encodeURIComponent(normalizedName)}`);
        state.editingSessionName = normalizedName;
        if (DOM.editTitle) {
            DOM.editTitle.textContent = i18n.t("sessions.editBindingFor", {
                session: normalizedName,
            });
        }
        renderCreateOptions();
        if (DOM.editCharacter) {
            DOM.editCharacter.value = String(detail.role_name || "");
        }
        if (DOM.editRouteMode) {
            DOM.editRouteMode.value = normalizeRouteMode(detail.route_mode || "chat_only");
        }
        if (DOM.editChannelType) {
            DOM.editChannelType.value = String(detail.channel_type || "");
        }
        if (DOM.editChannelIntegration) {
            DOM.editChannelIntegration.value = String(detail.channel_integration_id || "");
        }
        if (DOM.editForm) {
            DOM.editForm.hidden = false;
            DOM.editForm.scrollIntoView({ block: "nearest" });
        }
        setStatusKey("sessions.bindingReady", { session: normalizedName });
    } catch (error) {
        console.error(error);
        setRawStatus(i18n.t("sessions.bindingLoadFailed", {
            message: error.message || String(error),
        }));
    } finally {
        setBusy(false);
    }
}

async function saveSessionBinding() {
    const sessionName = state.editingSessionName;
    if (!sessionName || state.busy) {
        return;
    }
    const roleName = String((DOM.editCharacter && DOM.editCharacter.value) || "").trim();
    const routeMode = normalizeRouteMode(
        (DOM.editRouteMode && DOM.editRouteMode.value) || "",
    );
    const channelType = String((DOM.editChannelType && DOM.editChannelType.value) || "").trim();
    const channelIntegrationId = String(
        (DOM.editChannelIntegration && DOM.editChannelIntegration.value) || "",
    ).trim();
    setBusy(true);
    setStatusKey("sessions.savingBinding", { session: sessionName });
    try {
        if (roleName) {
            await requestJson(`/api/sessions/${encodeURIComponent(sessionName)}/role`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ role_name: roleName }),
            });
        }
        if (routeMode) {
            await requestJson(`/api/sessions/${encodeURIComponent(sessionName)}/route-mode`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ route_mode: routeMode }),
            });
        }
        await requestJson(`/api/sessions/${encodeURIComponent(sessionName)}/channel-binding`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                channel_type: channelType,
                channel_integration_id: channelIntegrationId,
            }),
        });
        clearEditForm();
        await loadSessions();
        setStatusKey("sessions.bindingSaved", { session: sessionName });
    } catch (error) {
        console.error(error);
        setRawStatus(i18n.t("sessions.bindingSaveFailed", {
            message: error.message || String(error),
        }));
    } finally {
        setBusy(false);
    }
}

function clearEditForm() {
    state.editingSessionName = "";
    if (DOM.editForm) {
        DOM.editForm.hidden = true;
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
    [DOM.create, DOM.refresh, DOM.editSave, DOM.editCancel].forEach((button) => {
        if (button) {
            button.disabled = isBusy;
        }
    });
    [
        DOM.createName,
        DOM.createCharacter,
        DOM.createRouteMode,
        DOM.createChannelType,
        DOM.createChannelIntegration,
        DOM.editCharacter,
        DOM.editRouteMode,
        DOM.editChannelType,
        DOM.editChannelIntegration,
    ].forEach((field) => {
        if (field) {
            field.disabled = isBusy;
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

import { initShellI18n } from "./shell-i18n.js?v=language-menu-1";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import {
    activeModelProfileFromConfig,
    applyModelProfileToLocalPreferences,
    modelProfileScopeFromConfig,
    notifyModelProfileChanged,
} from "./model-profile-runtime.js?v=model-profile-2";

const state = {
    payload: null,
    webConfig: null,
    selectedProfileId: "a",
    busy: false,
    loaded: false,
    loadError: "",
    statusKey: "",
    statusParams: {},
    statusRaw: "",
};

const DOM = {
    list: document.getElementById("model-profile-list"),
    create: document.getElementById("model-profile-create"),
    form: document.getElementById("model-profile-form"),
    title: document.getElementById("model-profile-title"),
    status: document.getElementById("model-profile-status"),
    activate: document.getElementById("model-profile-activate"),
    save: document.getElementById("model-profile-save"),
    remove: document.getElementById("model-profile-delete"),
    label: document.getElementById("model-profile-label"),
    chatProvider: document.getElementById("model-chat-provider"),
    chatModel: document.getElementById("model-chat-model"),
    chatBaseUrl: document.getElementById("model-chat-base-url"),
    chatApiKey: document.getElementById("model-chat-api-key"),
    chatApiKeyStatus: document.getElementById("model-chat-api-key-status"),
    chatClearApiKey: document.getElementById("model-chat-clear-api-key"),
    chatTemperature: document.getElementById("model-chat-temperature"),
    chatMaxTokens: document.getElementById("model-chat-max-tokens"),
};

const i18n = initShellI18n({
    onChange: () => {
        displayMode.refresh();
        render();
        refreshStatus();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });

DOM.form.addEventListener("submit", (event) => {
    event.preventDefault();
    void saveSelectedProfile();
});
DOM.activate.addEventListener("click", () => {
    void activateSelectedProfile();
});
DOM.create.addEventListener("click", () => {
    void createProfileFromSelection();
});
DOM.remove.addEventListener("click", () => {
    void deleteSelectedProfile();
});

void load();

async function load() {
    setBusy(true);
    state.loaded = false;
    state.loadError = "";
    setStatusKey("models.loading");
    try {
        const [payload, webConfig] = await Promise.all([
            requestJson("/api/model-profiles"),
            requestJson("/api/web/config"),
        ]);
        state.payload = payload;
        state.webConfig = webConfig;
        state.loaded = true;
        const activeProfile = activeModelProfileFromConfig({ model_profiles: payload });
        state.selectedProfileId = activeProfile ? activeProfile.profile_id : "a";
        render();
        setStatusKey("models.ready");
    } catch (error) {
        console.error(error);
        state.loaded = false;
        state.loadError = error.message || i18n.t("models.loadFailed");
        render();
        setRawStatus(error.message || i18n.t("models.loadFailed"));
    } finally {
        setBusy(false);
    }
}

function render() {
    renderProfileList();
    renderSelectedProfile();
}

function renderProfileList() {
    DOM.list.replaceChildren();
    const payload = state.payload;
    const profiles = Array.isArray(payload && payload.profiles) ? payload.profiles : [];
    profiles.forEach((profile) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "model-profile-card";
        button.classList.toggle("is-selected", profile.profile_id === state.selectedProfileId);
        button.classList.toggle("is-active", profile.profile_id === payload.active_profile_id);
        button.dataset.profileId = profile.profile_id;

        const code = document.createElement("strong");
        code.textContent = profileBadge(profile);
        const label = document.createElement("span");
        label.textContent = profile.label || profile.profile_id.toUpperCase();
        const status = document.createElement("small");
        status.textContent = profile.profile_id === payload.active_profile_id
            ? i18n.t("models.active")
            : i18n.t("models.inactive");

        button.append(code, label, status);
        button.addEventListener("click", () => {
            state.selectedProfileId = profile.profile_id;
            render();
        });
        DOM.list.appendChild(button);
    });
}

function renderSelectedProfile() {
    const profile = selectedProfile();
    DOM.title.textContent = `${profile.profile_id.toUpperCase()} · ${profile.label}`;
    DOM.label.value = profile.label || "";
    DOM.chatProvider.value = profile.chat.provider || "";
    DOM.chatModel.value = profile.chat.model || "";
    DOM.chatBaseUrl.value = profile.chat.base_url || "";
    DOM.chatApiKey.value = "";
    DOM.chatClearApiKey.checked = false;
    DOM.chatApiKeyStatus.textContent = apiKeyStatus(profile.chat);
    DOM.chatTemperature.value = profile.chat.temperature ?? "";
    DOM.chatMaxTokens.value = profile.chat.max_tokens ?? "";
    const disabled = formActionsDisabled();
    DOM.activate.disabled = disabled || profile.profile_id === activeProfileId();
    DOM.save.disabled = disabled;
    DOM.remove.disabled = disabled || !canDeleteSelectedProfile(profile);
}

function apiKeyStatus(section) {
    if (!section || !section.api_key_configured) {
        return i18n.t("models.apiKeyUnset");
    }
    if (section.api_key_source === "profile") {
        return i18n.t("models.apiKeyProfile");
    }
    if (section.api_key_source === "environment") {
        return i18n.t("models.apiKeyEnvironment");
    }
    return i18n.t("models.apiKeyConfigured");
}

function selectedProfile() {
    const payload = state.payload || { profiles: [] };
    return payload.profiles.find((item) => item.profile_id === state.selectedProfileId)
        || payload.profiles[0]
        || emptyProfile();
}

function activeProfileId() {
    return state.payload && state.payload.active_profile_id || "";
}

function modelProfileScope() {
    return modelProfileScopeFromConfig(state.webConfig);
}

function emptyProfile() {
    return {
        profile_id: "a",
        label: i18n.t("models.newProfileDefault", { count: 1 }),
        chat: {},
    };
}

async function createProfileFromSelection() {
    if (formActionsDisabled()) {
        return;
    }
    const sourceProfile = selectedProfile();
    const label = window.prompt(
        i18n.t("models.createPrompt"),
        nextProfileLabel(),
    );
    if (label === null) {
        return;
    }
    const cleanedLabel = String(label || "").trim();
    if (!cleanedLabel) {
        setStatusKey("models.createNameRequired");
        return;
    }

    setBusy(true);
    setStatusKey("models.creating");
    try {
        const created = await requestJson("/api/model-profiles", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                label: cleanedLabel,
                source_profile_id: sourceProfile.profile_id,
            }),
        });
        replaceProfile(created);
        state.selectedProfileId = created.profile_id;
        render();
        setStatusKey("models.created");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("models.createFailed"));
    } finally {
        setBusy(false);
    }
}

async function saveSelectedProfile() {
    if (formActionsDisabled()) {
        return;
    }
    const profile = selectedProfile();
    setBusy(true);
    setStatusKey("models.saving");
    try {
        const updated = await requestJson(`/api/model-profiles/${profile.profile_id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(profileRequestBody()),
        });
        replaceProfile(updated);
        if (updated.profile_id === activeProfileId()) {
            applyModelProfileToLocalPreferences(updated);
            notifyModelProfileChanged(updated.profile_id, modelProfileScope());
        }
        render();
        setStatusKey("models.saved");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("models.saveFailed"));
    } finally {
        setBusy(false);
    }
}

async function activateSelectedProfile() {
    if (formActionsDisabled()) {
        return;
    }
    const profile = selectedProfile();
    setBusy(true);
    setStatusKey("models.activating");
    try {
        const payload = await requestJson(`/api/model-profiles/${profile.profile_id}/activate`, {
            method: "POST",
        });
        applyModelProfilesPayload(payload, { notify: true });
        render();
        setStatusKey("models.activated");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("models.activateFailed"));
    } finally {
        setBusy(false);
    }
}

async function deleteSelectedProfile() {
    if (formActionsDisabled()) {
        return;
    }
    const profile = selectedProfile();
    if (!canDeleteSelectedProfile(profile)) {
        setStatusKey("models.deleteBlocked");
        return;
    }
    if (!window.confirm(i18n.t("models.deleteConfirm", { profile: profile.label || profile.profile_id }))) {
        return;
    }

    setBusy(true);
    setStatusKey("models.deleting");
    try {
        const payload = await requestJson(`/api/model-profiles/${profile.profile_id}`, {
            method: "DELETE",
        });
        applyModelProfilesPayload(payload);
        state.selectedProfileId = payload.active_profile_id
            || (Array.isArray(payload.profiles) && payload.profiles[0] && payload.profiles[0].profile_id)
            || "a";
        render();
        setStatusKey("models.deleted");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("models.deleteFailed"));
    } finally {
        setBusy(false);
    }
}

function profileRequestBody() {
    return {
        label: DOM.label.value,
        chat: {
            provider: DOM.chatProvider.value,
            model: DOM.chatModel.value,
            base_url: DOM.chatBaseUrl.value,
            temperature: optionalNumber(DOM.chatTemperature.value),
            max_tokens: optionalInteger(DOM.chatMaxTokens.value),
            api_key: DOM.chatApiKey.value,
            clear_api_key: DOM.chatClearApiKey.checked,
        },
    };
}

function replaceProfile(profile) {
    if (!state.payload || !Array.isArray(state.payload.profiles)) {
        return;
    }
    const index = state.payload.profiles.findIndex(
        (item) => item.profile_id === profile.profile_id,
    );
    if (index === -1) {
        state.payload.profiles.push(profile);
        return;
    }
    state.payload.profiles.splice(index, 1, profile);
}

function applyModelProfilesPayload(payload, options = {}) {
    state.payload = payload;
    const activeProfile = activeModelProfileFromConfig({ model_profiles: payload });
    if (activeProfile && options.notify) {
        applyModelProfileToLocalPreferences(activeProfile);
        notifyModelProfileChanged(activeProfile.profile_id, modelProfileScope());
    }
}

function optionalNumber(value) {
    const cleaned = String(value || "").trim();
    return cleaned ? Number(cleaned) : null;
}

function optionalInteger(value) {
    const cleaned = String(value || "").trim();
    return cleaned ? Number.parseInt(cleaned, 10) : null;
}

function setBusy(busy) {
    state.busy = Boolean(busy);
    DOM.form.classList.toggle("is-busy", state.busy);
    const disabled = formActionsDisabled();
    const profile = selectedProfile();
    DOM.create.disabled = disabled;
    DOM.activate.disabled = disabled || profile.profile_id === activeProfileId();
    DOM.save.disabled = disabled;
    DOM.remove.disabled = disabled || !canDeleteSelectedProfile(profile);
}

function setStatusKey(key, params = {}) {
    state.statusKey = key;
    state.statusParams = params;
    state.statusRaw = "";
    refreshStatus();
}

function setRawStatus(message) {
    state.statusKey = "";
    state.statusParams = {};
    state.statusRaw = String(message || "");
    refreshStatus();
}

function refreshStatus() {
    DOM.status.textContent = state.statusKey
        ? i18n.t(state.statusKey, state.statusParams)
        : state.statusRaw;
}

function formActionsDisabled() {
    return state.busy || !state.loaded || Boolean(state.loadError);
}

function canDeleteSelectedProfile(profile = selectedProfile()) {
    const payload = state.payload || { profiles: [] };
    const profileCount = Array.isArray(payload.profiles) ? payload.profiles.length : 0;
    return Boolean(
        profile
        && profile.profile_id
        && profile.profile_id !== activeProfileId()
        && profileCount > 1,
    );
}

function nextProfileLabel() {
    const count = state.payload && Array.isArray(state.payload.profiles)
        ? state.payload.profiles.length + 1
        : 1;
    return i18n.t("models.newProfileDefault", { count });
}

function profileBadge(profile) {
    const label = String(profile.label || profile.profile_id || "").trim();
    const words = label.match(/[A-Za-z0-9]+/g) || [];
    if (words.length >= 2) {
        return `${words[0][0]}${words[1][0]}`.toUpperCase();
    }
    if (words.length === 1) {
        return words[0].slice(0, 2).toUpperCase();
    }
    return String(profile.profile_id || "?").slice(0, 2).toUpperCase();
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            Accept: "application/json",
            ...(options.headers || {}),
        },
    });
    if (!response.ok) {
        let detail = response.statusText;
        try {
            const payload = await response.json();
            detail = payload.detail || detail;
        } catch (_error) {
            // Keep statusText when the response is not JSON.
        }
        throw new Error(detail);
    }
    return response.json();
}

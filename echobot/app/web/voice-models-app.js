import { initShellI18n } from "./shell-i18n.js?v=session-centered-2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import {
    applyModelProfileToLocalPreferences,
    modelProfileScopeFromConfig,
    notifyModelProfileChanged,
} from "./model-profile-runtime.js?v=model-profile-2";

const state = {
    payload: null,
    voicePayload: null,
    webConfig: null,
    selectedProfileId: "a",
    busy: false,
    loaded: false,
    loadError: "",
    statusKey: "",
    statusRaw: "",
};

const DOM = {
    list: document.getElementById("voice-profile-list"),
    create: document.getElementById("voice-profile-create"),
    form: document.getElementById("voice-profile-form"),
    title: document.getElementById("voice-profile-title"),
    status: document.getElementById("voice-profile-status"),
    activate: document.getElementById("voice-profile-activate"),
    save: document.getElementById("voice-profile-save"),
    remove: document.getElementById("voice-profile-delete"),
    label: document.getElementById("voice-profile-label"),
    ttsProvider: document.getElementById("voice-tts-provider"),
    ttsModel: document.getElementById("voice-tts-model"),
    ttsBaseUrl: document.getElementById("voice-tts-base-url"),
    ttsApiKey: document.getElementById("voice-tts-api-key"),
    ttsApiKeyStatus: document.getElementById("voice-tts-api-key-status"),
    ttsClearApiKey: document.getElementById("voice-tts-clear-api-key"),
    ttsVoice: document.getElementById("voice-tts-voice"),
    sttProvider: document.getElementById("voice-stt-provider"),
    sttModel: document.getElementById("voice-stt-model"),
    sttBaseUrl: document.getElementById("voice-stt-base-url"),
    sttApiKey: document.getElementById("voice-stt-api-key"),
    sttApiKeyStatus: document.getElementById("voice-stt-api-key-status"),
    sttClearApiKey: document.getElementById("voice-stt-clear-api-key"),
    sttLanguage: document.getElementById("voice-stt-language"),
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
        const [payload, voicePayload, webConfig] = await Promise.all([
            requestJson("/api/model-profiles"),
            requestJson("/api/voice-models"),
            requestJson("/api/web/config"),
        ]);
        state.payload = payload;
        state.voicePayload = voicePayload;
        state.webConfig = webConfig;
        state.selectedProfileId = voicePayload.active_voice_profile_id || payload.active_profile_id || "a";
        state.loaded = true;
        render();
        setStatusKey("models.ready");
    } catch (error) {
        console.error(error);
        state.loadError = error.message || i18n.t("models.loadFailed");
        render();
        setRawStatus(state.loadError);
    } finally {
        setBusy(false);
    }
}

function render() {
    renderProfileList();
    renderProviderOptions();
    renderSelectedProfile();
}

function renderProfileList() {
    DOM.list.replaceChildren();
    voiceProfiles().forEach((profile) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "model-profile-card";
        button.classList.toggle("is-selected", profile.id === state.selectedProfileId);
        button.classList.toggle("is-active", profile.id === activeProfileId());

        const code = document.createElement("strong");
        code.textContent = profileBadge(profile);
        const label = document.createElement("span");
        label.textContent = profile.name || profile.id.toUpperCase();
        const status = document.createElement("small");
        status.textContent = profile.id === activeProfileId()
            ? i18n.t("models.active")
            : i18n.t("models.inactive");

        button.append(code, label, status);
        button.addEventListener("click", () => {
            state.selectedProfileId = profile.id;
            render();
        });
        DOM.list.appendChild(button);
    });
}

function renderProviderOptions() {
    renderSelectOptions(DOM.ttsProvider, ttsProviderOptions(), selectedProfile().tts.provider);
    renderSelectOptions(DOM.sttProvider, sttProviderOptions(), selectedProfile().stt.provider);
}

function renderSelectOptions(select, options, selectedValue) {
    select.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t("models.keepDefault");
    select.appendChild(emptyOption);
    options.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.label;
        select.appendChild(option);
    });
    select.value = selectedValue || "";
}

function renderSelectedProfile() {
    const profile = selectedProfile();
    DOM.title.textContent = `${profile.id.toUpperCase()} · ${profile.name}`;
    DOM.label.value = profile.name || "";
    DOM.ttsModel.value = profile.tts.model || "";
    DOM.ttsBaseUrl.value = profile.tts.base_url || "";
    DOM.ttsVoice.value = profile.tts.voice || "";
    DOM.ttsApiKey.value = "";
    DOM.ttsClearApiKey.checked = false;
    DOM.ttsApiKeyStatus.textContent = apiKeyStatus(profile.tts);
    DOM.sttModel.value = profile.stt.model || "";
    DOM.sttBaseUrl.value = profile.stt.base_url || "";
    DOM.sttLanguage.value = profile.stt.language || "";
    DOM.sttApiKey.value = "";
    DOM.sttClearApiKey.checked = false;
    DOM.sttApiKeyStatus.textContent = apiKeyStatus(profile.stt);
    const disabled = formActionsDisabled();
    DOM.create.disabled = disabled;
    DOM.activate.disabled = disabled || profile.id === activeProfileId();
    DOM.save.disabled = disabled;
    DOM.remove.disabled = disabled || !canDeleteSelectedProfile(profile);
}

async function createProfileFromSelection() {
    if (formActionsDisabled()) {
        return;
    }
    const label = window.prompt(i18n.t("models.createPrompt"), nextProfileLabel());
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
                source_profile_id: selectedProfile().id,
            }),
        });
        state.selectedProfileId = created.profile_id;
        await load();
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
        const updated = await requestJson(`/api/model-profiles/${profile.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                label: DOM.label.value,
                tts: {
                    provider: DOM.ttsProvider.value,
                    model: DOM.ttsModel.value,
                    base_url: DOM.ttsBaseUrl.value,
                    voice: DOM.ttsVoice.value,
                    api_key: DOM.ttsApiKey.value,
                    clear_api_key: DOM.ttsClearApiKey.checked,
                },
                asr: {
                    provider: DOM.sttProvider.value,
                    model: DOM.sttModel.value,
                    base_url: DOM.sttBaseUrl.value,
                    language: DOM.sttLanguage.value,
                    api_key: DOM.sttApiKey.value,
                    clear_api_key: DOM.sttClearApiKey.checked,
                },
            }),
        });
        if (updated.profile_id === activeProfileId()) {
            applyModelProfileToLocalPreferences(updated);
            notifyModelProfileChanged(updated.profile_id, modelProfileScope());
        }
        await load();
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
        const payload = await requestJson(`/api/model-profiles/${profile.id}/activate`, {
            method: "POST",
        });
        state.payload = payload;
        const activeProfile = payload.profiles.find((item) => item.profile_id === payload.active_profile_id);
        if (activeProfile) {
            applyModelProfileToLocalPreferences(activeProfile);
            notifyModelProfileChanged(activeProfile.profile_id, modelProfileScope());
        }
        await load();
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
    if (!window.confirm(i18n.t("models.deleteConfirm", { profile: profile.name || profile.id }))) {
        return;
    }
    setBusy(true);
    setStatusKey("models.deleting");
    try {
        await requestJson(`/api/model-profiles/${profile.id}`, { method: "DELETE" });
        state.selectedProfileId = activeProfileId() || "a";
        await load();
        setStatusKey("models.deleted");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("models.deleteFailed"));
    } finally {
        setBusy(false);
    }
}

function selectedProfile() {
    return voiceProfiles().find((item) => item.id === state.selectedProfileId)
        || voiceProfiles()[0]
        || emptyProfile();
}

function voiceProfiles() {
    return state.voicePayload && Array.isArray(state.voicePayload.profiles)
        ? state.voicePayload.profiles
        : [];
}

function activeProfileId() {
    return state.payload && state.payload.active_profile_id || "";
}

function modelProfileScope() {
    return modelProfileScopeFromConfig(state.webConfig);
}

function emptyProfile() {
    return {
        id: "a",
        name: i18n.t("models.newProfileDefault", { count: 1 }),
        tts: {},
        stt: {},
    };
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

function ttsProviderOptions() {
    const providers = state.webConfig && state.webConfig.tts && Array.isArray(state.webConfig.tts.providers)
        ? state.webConfig.tts.providers
        : [];
    return providers.map((item) => ({
        value: item.name,
        label: item.available ? item.label : `${item.label} (${i18n.t("models.notReady")})`,
    }));
}

function sttProviderOptions() {
    const providers = state.webConfig && state.webConfig.asr && Array.isArray(state.webConfig.asr.asr_providers)
        ? state.webConfig.asr.asr_providers
        : [];
    return providers.map((item) => ({
        value: item.name,
        label: item.available ? item.label : `${item.label} (${i18n.t("models.notReady")})`,
    }));
}

function canDeleteSelectedProfile(profile = selectedProfile()) {
    const profiles = voiceProfiles();
    return Boolean(profile && profile.id && profile.id !== activeProfileId() && profiles.length > 1);
}

function nextProfileLabel() {
    return i18n.t("models.newProfileDefault", { count: voiceProfiles().length + 1 });
}

function profileBadge(profile) {
    const label = String(profile.name || profile.id || "").trim();
    const words = label.match(/[A-Za-z0-9]+/g) || [];
    if (words.length >= 2) {
        return `${words[0][0]}${words[1][0]}`.toUpperCase();
    }
    if (words.length === 1) {
        return words[0].slice(0, 2).toUpperCase();
    }
    return String(profile.id || "?").slice(0, 2).toUpperCase();
}

function setBusy(busy) {
    state.busy = Boolean(busy);
    DOM.form.classList.toggle("is-busy", state.busy);
}

function setStatusKey(key) {
    state.statusKey = key;
    state.statusRaw = "";
    refreshStatus();
}

function setRawStatus(message) {
    state.statusKey = "";
    state.statusRaw = String(message || "");
    refreshStatus();
}

function refreshStatus() {
    DOM.status.textContent = state.statusKey ? i18n.t(state.statusKey) : state.statusRaw;
}

function formActionsDisabled() {
    return state.busy || !state.loaded || Boolean(state.loadError);
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
            // Keep statusText when response body is not JSON.
        }
        throw new Error(detail);
    }
    return response.json();
}

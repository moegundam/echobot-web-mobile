import { initShellI18n } from "./shell-i18n.js?v=language-menu-1&uiux=2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import {
    activeModelProfileFromConfig,
    applyModelProfileToLocalPreferences,
    modelProfileScopeFromConfig,
    notifyModelProfileChanged,
} from "./model-profile-runtime.js?v=model-profile-2";
import { requestJson } from "./modules/api.js";
import { createDirtyFormGuard } from "./modules/dirty-form-guard.js";

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

let committedLanguage = "";
const i18n = initShellI18n({
    onChange: (nextLanguage) => {
        displayMode.refresh();
        if (!dirtyGuard.confirmDiscard()) {
            restoreLanguage(committedLanguage);
            return;
        }
        committedLanguage = nextLanguage;
        render();
        refreshStatus();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
const dirtyGuard = createDirtyFormGuard({
    form: DOM.form,
    confirmDiscard: () => window.confirm(i18n.t("admin.unsavedChangesConfirm")),
});
committedLanguage = i18n.language;

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

async function load(options = {}) {
    setBusy(true);
    state.loaded = false;
    state.loadError = "";
    setStatusKey("models.loading");
    try {
        const [voicePayload, webConfig] = await Promise.all([
            requestJson("/api/voice-models"),
            requestJson("/api/web/config"),
        ]);
        state.payload = modelProfilesPayloadFromConfig(webConfig);
        state.voicePayload = voicePayload;
        state.webConfig = webConfig;
        state.selectedProfileId = resolveExistingProfileId(
            options.selectedProfileId,
            voicePayload,
        ) || resolveExistingProfileId(
            state.selectedProfileId,
            voicePayload,
        ) || voicePayload.active_voice_profile_id || state.payload.active_profile_id || "a";
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
            if (profile.id === state.selectedProfileId || !dirtyGuard.confirmDiscard()) {
                return;
            }
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
    if (!dirtyGuard.confirmDiscard()) {
        return;
    }
    setBusy(true);
    setStatusKey("models.creating");
    try {
        const created = await requestJson("/api/voice-models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: cleanedLabel,
                source_profile_id: selectedProfile().id,
            }),
        });
        await load({ selectedProfileId: created.id });
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
        const updated = await requestJson(`/api/voice-models/${profile.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: DOM.label.value,
                tts: {
                    provider: DOM.ttsProvider.value,
                    model: DOM.ttsModel.value,
                    base_url: DOM.ttsBaseUrl.value,
                    voice: DOM.ttsVoice.value,
                    api_key: DOM.ttsApiKey.value,
                    clear_api_key: DOM.ttsClearApiKey.checked,
                },
                stt: {
                    provider: DOM.sttProvider.value,
                    model: DOM.sttModel.value,
                    base_url: DOM.sttBaseUrl.value,
                    language: DOM.sttLanguage.value,
                    api_key: DOM.sttApiKey.value,
                    clear_api_key: DOM.sttClearApiKey.checked,
                },
            }),
        });
        if (updated.id === activeProfileId()) {
            await refreshRuntimeModelSnapshot({ notify: true });
        }
        await load({ selectedProfileId: updated.id });
        if (state.loaded) {
            dirtyGuard.clear();
        }
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
    if (!dirtyGuard.confirmDiscard()) {
        return;
    }
    const profile = selectedProfile();
    setBusy(true);
    setStatusKey("models.activating");
    try {
        await requestJson(`/api/voice-models/${profile.id}/activate`, {
            method: "POST",
        });
        await refreshRuntimeModelSnapshot({ notify: true });
        await load({ selectedProfileId: profile.id });
        if (state.loaded) {
            dirtyGuard.clear();
        }
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
    if (!dirtyGuard.confirmDiscard()) {
        return;
    }
    setBusy(true);
    setStatusKey("models.deleting");
    try {
        await requestJson(`/api/voice-models/${profile.id}`, { method: "DELETE" });
        await load({ selectedProfileId: activeProfileId() || "a" });
        if (state.loaded) {
            dirtyGuard.clear();
        }
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

function resolveExistingProfileId(profileId, voicePayload = state.voicePayload) {
    const normalizedId = String(profileId || "").trim();
    if (!normalizedId) {
        return "";
    }
    const profiles = voicePayload && Array.isArray(voicePayload.profiles)
        ? voicePayload.profiles
        : [];
    return profiles.some((item) => item.id === normalizedId) ? normalizedId : "";
}

function voiceProfiles() {
    return state.voicePayload && Array.isArray(state.voicePayload.profiles)
        ? state.voicePayload.profiles
        : [];
}

function activeProfileId() {
    return state.voicePayload && state.voicePayload.active_voice_profile_id || "";
}

function modelProfileScope() {
    return modelProfileScopeFromConfig(state.webConfig);
}

async function refreshRuntimeModelSnapshot(options = {}) {
    state.webConfig = await requestJson("/api/web/config");
    const payload = modelProfilesPayloadFromConfig(state.webConfig);
    state.payload = payload;
    const activeProfile = activeModelProfileFromConfig({ model_profiles: payload });
    if (activeProfile && options.notify) {
        applyModelProfileToLocalPreferences(activeProfile);
        notifyModelProfileChanged(activeProfile.profile_id, modelProfileScope());
    }
    return payload;
}

function modelProfilesPayloadFromConfig(config) {
    return config && config.model_profiles || {
        active_profile_id: "",
        role_bindings: {},
        profiles: [],
    };
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
    const disabled = formActionsDisabled();
    const profile = selectedProfile();
    DOM.create.disabled = disabled;
    DOM.activate.disabled = disabled || profile.id === activeProfileId();
    DOM.save.disabled = disabled;
    DOM.remove.disabled = disabled || !canDeleteSelectedProfile(profile);
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

function restoreLanguage(language) {
    if (!language || i18n.language === language) {
        return;
    }
    i18n.language = language;
    try {
        window.localStorage.setItem("echobot.shell.language", language);
    } catch (_error) {
        // localStorage can be unavailable in restricted browsing contexts.
    }
    i18n.apply();
    displayMode.refresh();
    refreshStatus();
}

function formActionsDisabled() {
    return state.busy || !state.loaded || Boolean(state.loadError);
}

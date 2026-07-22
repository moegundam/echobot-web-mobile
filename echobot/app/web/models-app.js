import { initShellI18n } from "./shell-i18n.js?v=language-menu-1&uiux=2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import {
    activeModelProfileFromConfig,
    applyModelProfileToLocalPreferences,
    modelProfileScopeFromConfig,
    notifyModelProfileChanged,
} from "./model-profile-runtime.js?v=model-profile-2";
import { requestErrorMessage, requestJson } from "./modules/api.js";
import { createDirtyFormGuard } from "./modules/dirty-form-guard.js";

const LLM_SMOKE_ACTION = "/smoke";

const state = {
    payload: null,
    llmPayload: null,
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
    smoke: document.getElementById("model-profile-smoke"),
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
DOM.smoke.addEventListener("click", () => {
    void smokeSelectedProfile();
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
        const [llmPayload, webConfig] = await Promise.all([
            requestJson("/api/llm-models"),
            requestJson("/api/web/config"),
        ]);
        state.payload = modelProfilesPayloadFromConfig(webConfig);
        state.llmPayload = llmPayload;
        state.webConfig = webConfig;
        state.loaded = true;
        state.selectedProfileId = resolveExistingProfileId(options.selectedProfileId)
            || resolveExistingProfileId(state.selectedProfileId)
            || activeProfileId()
            || "a";
        render();
        setStatusKey("models.settingsLoaded");
    } catch (error) {
        console.error(error);
        state.loaded = false;
        state.loadError = requestErrorMessage(error, i18n.t, "models.loadFailed");
        render();
        setRawStatus(state.loadError);
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
    const profiles = llmProfiles();
    profiles.forEach((profile) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "model-profile-card";
        button.classList.toggle("is-selected", profile.profile_id === state.selectedProfileId);
        button.classList.toggle("is-active", profile.profile_id === activeProfileId());
        button.dataset.profileId = profile.profile_id;

        const code = document.createElement("strong");
        code.textContent = profileBadge(profile);
        const label = document.createElement("span");
        label.textContent = profile.label || profile.profile_id.toUpperCase();
        const status = document.createElement("small");
        status.textContent = profile.profile_id === activeProfileId()
            ? i18n.t("models.active")
            : i18n.t("models.inactive");

        button.append(code, label, status);
        button.addEventListener("click", () => {
            if (profile.profile_id === state.selectedProfileId || !dirtyGuard.confirmDiscard()) {
                return;
            }
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
    DOM.smoke.disabled = disabled;
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
    const profiles = llmProfiles();
    return profiles.find((item) => item.profile_id === state.selectedProfileId)
        || profiles[0]
        || emptyProfile();
}

function resolveExistingProfileId(profileId) {
    const normalizedId = String(profileId || "").trim();
    const profiles = llmProfiles();
    if (!normalizedId || !profiles.length) {
        return "";
    }
    return profiles.some((item) => item.profile_id === normalizedId)
        ? normalizedId
        : "";
}

function activeProfileId() {
    return state.llmPayload && state.llmPayload.active_model_id || "";
}

function llmProfiles() {
    const models = state.llmPayload && Array.isArray(state.llmPayload.models)
        ? state.llmPayload.models
        : [];
    return models.map((model) => ({
        profile_id: model.id,
        label: model.name,
        chat: {
            provider: model.provider,
            model: model.model,
            base_url: model.base_url,
            temperature: model.temperature,
            max_tokens: model.max_tokens,
            api_key_configured: model.api_key_configured,
            api_key_source: model.api_key_source,
        },
    }));
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
    if (!dirtyGuard.confirmDiscard()) {
        return;
    }

    setBusy(true);
    setStatusKey("models.creating");
    try {
        const created = await requestJson("/api/llm-models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: cleanedLabel,
                source_model_id: sourceProfile.profile_id,
            }),
        });
        await load({ selectedProfileId: created.id });
        setStatusKey("models.created");
    } catch (error) {
        console.error(error);
        setRawStatus(requestErrorMessage(error, i18n.t, "models.createFailed"));
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
        const updated = await requestJson(`/api/llm-models/${profile.profile_id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(profileRequestBody()),
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
        setRawStatus(requestErrorMessage(error, i18n.t, "models.saveFailed"));
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
        await requestJson(`/api/llm-models/${profile.profile_id}/activate`, {
            method: "POST",
        });
        await refreshRuntimeModelSnapshot({ notify: true });
        await load({ selectedProfileId: profile.profile_id });
        if (state.loaded) {
            dirtyGuard.clear();
        }
        setStatusKey("models.activated");
    } catch (error) {
        console.error(error);
        setRawStatus(requestErrorMessage(error, i18n.t, "models.activateFailed"));
    } finally {
        setBusy(false);
    }
}

async function smokeSelectedProfile() {
    if (formActionsDisabled()) {
        return;
    }
    if (dirtyGuard.isDirty()) {
        setStatusKey("models.smokeSaveFirst");
        return;
    }
    const profile = selectedProfile();
    setBusy(true);
    setStatusKey("models.smokeTesting");
    try {
        const result = await requestJson(
            `/api/llm-models/${encodeURIComponent(profile.profile_id)}${LLM_SMOKE_ACTION}`,
            { method: "POST" },
        );
        if (!result || result.ok !== true) {
            setStatusKey("models.smokeFailed");
            return;
        }
        setStatusKey("models.smokeReady", {
            model: result.model || profile.chat.model || profile.label,
        });
    } catch (error) {
        console.error(error);
        setRawStatus(requestErrorMessage(error, i18n.t, "models.smokeFailed"));
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
    if (!dirtyGuard.confirmDiscard()) {
        return;
    }

    setBusy(true);
    setStatusKey("models.deleting");
    try {
        const payload = await requestJson(`/api/llm-models/${profile.profile_id}`, {
            method: "DELETE",
        });
        await load({ selectedProfileId: payload.active_model_id || "a" });
        if (state.loaded) {
            dirtyGuard.clear();
        }
        setStatusKey("models.deleted");
    } catch (error) {
        console.error(error);
        setRawStatus(requestErrorMessage(error, i18n.t, "models.deleteFailed"));
    } finally {
        setBusy(false);
    }
}

function profileRequestBody() {
    return {
        name: DOM.label.value,
        provider: DOM.chatProvider.value,
        model: DOM.chatModel.value,
        base_url: DOM.chatBaseUrl.value,
        temperature: optionalNumber(DOM.chatTemperature.value),
        max_tokens: optionalInteger(DOM.chatMaxTokens.value),
        api_key: DOM.chatApiKey.value,
        clear_api_key: DOM.chatClearApiKey.checked,
    };
}

function applyModelProfilesPayload(payload, options = {}) {
    state.payload = payload;
    const activeProfile = activeModelProfileFromConfig({ model_profiles: payload });
    if (activeProfile && options.notify) {
        applyModelProfileToLocalPreferences(activeProfile);
        notifyModelProfileChanged(activeProfile.profile_id, modelProfileScope());
    }
}

async function refreshRuntimeModelSnapshot(options = {}) {
    state.webConfig = await requestJson("/api/web/config");
    const payload = modelProfilesPayloadFromConfig(state.webConfig);
    applyModelProfilesPayload(payload, options);
    return payload;
}

function modelProfilesPayloadFromConfig(config) {
    return config && config.model_profiles || {
        active_profile_id: "",
        role_bindings: {},
        profiles: [],
    };
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
    DOM.smoke.disabled = disabled;
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

function canDeleteSelectedProfile(profile = selectedProfile()) {
    const profileCount = llmProfiles().length;
    return Boolean(
        profile
        && profile.profile_id
        && profile.profile_id !== activeProfileId()
        && profileCount > 1,
    );
}

function nextProfileLabel() {
    const count = llmProfiles().length + 1;
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

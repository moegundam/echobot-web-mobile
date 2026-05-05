import { initShellI18n } from "./shell-i18n.js?v=admin-boundary-1";
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
    roles: [],
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
    roleBindings: document.getElementById("model-role-binding-list"),
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
    ttsProvider: document.getElementById("model-tts-provider"),
    ttsModel: document.getElementById("model-tts-model"),
    ttsBaseUrl: document.getElementById("model-tts-base-url"),
    ttsApiKey: document.getElementById("model-tts-api-key"),
    ttsApiKeyStatus: document.getElementById("model-tts-api-key-status"),
    ttsClearApiKey: document.getElementById("model-tts-clear-api-key"),
    ttsVoice: document.getElementById("model-tts-voice"),
    asrProvider: document.getElementById("model-asr-provider"),
    asrModel: document.getElementById("model-asr-model"),
    asrBaseUrl: document.getElementById("model-asr-base-url"),
    asrApiKey: document.getElementById("model-asr-api-key"),
    asrApiKeyStatus: document.getElementById("model-asr-api-key-status"),
    asrClearApiKey: document.getElementById("model-asr-clear-api-key"),
    asrLanguage: document.getElementById("model-asr-language"),
    live2dSelection: document.getElementById("model-live2d-selection"),
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
        const [payload, webConfig, roles] = await Promise.all([
            requestJson("/api/model-profiles"),
            requestJson("/api/web/config"),
            requestJson("/api/roles"),
        ]);
        state.payload = payload;
        state.webConfig = webConfig;
        state.roles = Array.isArray(roles) ? roles : [];
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
    renderRoleBindings();
    renderProviderOptions();
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

function renderRoleBindings() {
    DOM.roleBindings.replaceChildren();
    const roles = Array.isArray(state.roles) ? state.roles : [];
    const profiles = state.payload && Array.isArray(state.payload.profiles)
        ? state.payload.profiles
        : [];
    if (roles.length === 0 || profiles.length === 0) {
        const empty = document.createElement("p");
        empty.className = "model-role-binding-empty";
        empty.textContent = i18n.t("models.noRoleBindings");
        DOM.roleBindings.appendChild(empty);
        return;
    }

    roles.forEach((role) => {
        const roleName = String(role && role.name || "").trim();
        if (!roleName) {
            return;
        }

        const row = document.createElement("label");
        row.className = "model-role-binding-row";

        const text = document.createElement("span");
        text.textContent = roleName === "default"
            ? i18n.t("console.defaultRoleOption", { role: roleName })
            : roleName;

        const select = document.createElement("select");
        select.disabled = formActionsDisabled();
        renderRoleBindingOptions(select, profiles, roleBindingProfileId(roleName));
        select.addEventListener("change", () => {
            void saveRoleBinding(roleName, select.value);
        });

        row.append(text, select);
        DOM.roleBindings.appendChild(row);
    });
}

function renderRoleBindingOptions(select, profiles, selectedProfileId) {
    select.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t("models.useActiveProfile");
    select.appendChild(emptyOption);

    profiles.forEach((profile) => {
        const option = document.createElement("option");
        option.value = profile.profile_id;
        option.textContent = `${profile.profile_id.toUpperCase()} · ${profile.label || profile.profile_id}`;
        select.appendChild(option);
    });

    select.value = selectedProfileId || "";
}

function renderProviderOptions() {
    renderSelectOptions(
        DOM.ttsProvider,
        ttsProviderOptions(),
        selectedProfile().tts.provider,
    );
    renderSelectOptions(
        DOM.asrProvider,
        asrProviderOptions(),
        selectedProfile().asr.provider,
    );
    renderSelectOptions(
        DOM.live2dSelection,
        live2dOptions(),
        selectedProfile().live2d.selection_key,
    );
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
    DOM.ttsModel.value = profile.tts.model || "";
    DOM.ttsBaseUrl.value = profile.tts.base_url || "";
    DOM.ttsApiKey.value = "";
    DOM.ttsClearApiKey.checked = false;
    DOM.ttsApiKeyStatus.textContent = apiKeyStatus(profile.tts);
    DOM.ttsVoice.value = profile.tts.voice || "";
    DOM.asrModel.value = profile.asr.model || "";
    DOM.asrBaseUrl.value = profile.asr.base_url || "";
    DOM.asrApiKey.value = "";
    DOM.asrClearApiKey.checked = false;
    DOM.asrApiKeyStatus.textContent = apiKeyStatus(profile.asr);
    DOM.asrLanguage.value = profile.asr.language || "";
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
        tts: {},
        asr: {},
        live2d: {},
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

async function saveRoleBinding(roleName, profileId) {
    if (formActionsDisabled()) {
        return;
    }

    setBusy(true);
    setStatusKey("models.savingRoleBinding");
    try {
        const encodedRoleName = encodeURIComponent(roleName);
        const payload = profileId
            ? await requestJson(`/api/model-profiles/role-bindings/${encodedRoleName}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile_id: profileId }),
            })
            : await requestJson(`/api/model-profiles/role-bindings/${encodedRoleName}`, {
                method: "DELETE",
            });
        const previousActiveProfileId = activeProfileId();
        applyModelProfilesPayload(payload, {
            notify: payload.active_profile_id !== previousActiveProfileId,
        });
        render();
        setStatusKey("models.roleBindingSaved");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("models.roleBindingFailed"));
        render();
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
        tts: {
            provider: DOM.ttsProvider.value,
            model: DOM.ttsModel.value,
            base_url: DOM.ttsBaseUrl.value,
            voice: DOM.ttsVoice.value,
            api_key: DOM.ttsApiKey.value,
            clear_api_key: DOM.ttsClearApiKey.checked,
        },
        asr: {
            provider: DOM.asrProvider.value,
            model: DOM.asrModel.value,
            base_url: DOM.asrBaseUrl.value,
            language: DOM.asrLanguage.value,
            api_key: DOM.asrApiKey.value,
            clear_api_key: DOM.asrClearApiKey.checked,
        },
        live2d: {
            selection_key: DOM.live2dSelection.value,
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

function roleBindingProfileId(roleName) {
    const bindings = state.payload && state.payload.role_bindings
        && typeof state.payload.role_bindings === "object"
        ? state.payload.role_bindings
        : {};
    return String(bindings[roleName] || "");
}

function ttsProviderOptions() {
    const providers = state.webConfig
        && state.webConfig.tts
        && Array.isArray(state.webConfig.tts.providers)
        ? state.webConfig.tts.providers
        : [];
    return providers.map((item) => ({
        value: item.name,
        label: item.available ? item.label : `${item.label} (${i18n.t("models.notReady")})`,
    }));
}

function asrProviderOptions() {
    const providers = state.webConfig
        && state.webConfig.asr
        && Array.isArray(state.webConfig.asr.asr_providers)
        ? state.webConfig.asr.asr_providers
        : [];
    return providers.map((item) => ({
        value: item.name,
        label: item.available ? item.label : `${item.label} (${i18n.t("models.notReady")})`,
    }));
}

function live2dOptions() {
    const models = state.webConfig
        && state.webConfig.live2d
        && Array.isArray(state.webConfig.live2d.models)
        ? state.webConfig.live2d.models
        : [];
    return models.map((item) => ({
        value: item.selection_key,
        label: item.model_name || item.directory_name || item.selection_key,
    }));
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
    DOM.roleBindings.querySelectorAll("select").forEach((select) => {
        select.disabled = disabled;
    });
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

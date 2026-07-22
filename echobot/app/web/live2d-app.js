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
    live2dPayload: null,
    webConfig: null,
    selectedProfileId: "a",
    busy: false,
    loaded: false,
    loadError: "",
    statusKey: "",
    statusRaw: "",
};

const DOM = {
    list: document.getElementById("live2d-profile-list"),
    create: document.getElementById("live2d-profile-create"),
    form: document.getElementById("live2d-profile-form"),
    title: document.getElementById("live2d-profile-title"),
    status: document.getElementById("live2d-profile-status"),
    activate: document.getElementById("live2d-profile-activate"),
    save: document.getElementById("live2d-profile-save"),
    remove: document.getElementById("live2d-profile-delete"),
    label: document.getElementById("live2d-profile-label"),
    selection: document.getElementById("live2d-selection"),
    detail: document.getElementById("live2d-selection-detail"),
    catalog: document.getElementById("live2d-catalog-list"),
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
        const [live2dPayload, webConfig] = await Promise.all([
            requestJson("/api/live2d-models"),
            requestJson("/api/web/config"),
        ]);
        state.payload = modelProfilesPayloadFromConfig(webConfig);
        state.live2dPayload = live2dPayload;
        state.webConfig = webConfig;
        state.selectedProfileId = resolveExistingProfileId(
            options.selectedProfileId,
            live2dPayload,
        ) || resolveExistingProfileId(
            state.selectedProfileId,
            live2dPayload,
        ) || live2dPayload.active_live2d_model_id || state.payload.active_profile_id || "a";
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
    renderSelectionOptions();
    renderSelectedProfile();
    renderCatalog();
}

function renderProfileList() {
    DOM.list.replaceChildren();
    live2dProfiles().forEach((profile) => {
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
        status.textContent = profile.selection_key || i18n.t("models.keepDefault");

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

function renderSelectionOptions() {
    DOM.selection.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t("models.keepDefault");
    DOM.selection.appendChild(emptyOption);
    catalog().forEach((item) => {
        const option = document.createElement("option");
        option.value = item.selection_key;
        option.textContent = item.model_name || item.directory_name || item.selection_key;
        DOM.selection.appendChild(option);
    });
}

function renderSelectedProfile() {
    const profile = selectedProfile();
    DOM.title.textContent = `${profile.id.toUpperCase()} · ${profile.name}`;
    DOM.label.value = profile.name || "";
    DOM.selection.value = profile.selection_key || "";
    DOM.detail.textContent = profile.available
        ? i18n.t("live2dAdmin.available", { model: profile.model_name || profile.selection_key })
        : i18n.t("live2dAdmin.unavailable");
    const disabled = formActionsDisabled();
    DOM.create.disabled = disabled;
    DOM.activate.disabled = disabled || profile.id === activeProfileId();
    DOM.save.disabled = disabled;
    DOM.remove.disabled = disabled || !canDeleteSelectedProfile(profile);
}

function renderCatalog() {
    DOM.catalog.replaceChildren();
    catalog().forEach((item) => {
        const card = document.createElement("article");
        card.className = "model-profile-card";
        const code = document.createElement("strong");
        code.textContent = "L2";
        const title = document.createElement("span");
        title.textContent = item.model_name || item.directory_name || item.selection_key;
        const meta = document.createElement("small");
        meta.textContent = item.selection_key || "";
        card.append(code, title, meta);
        DOM.catalog.appendChild(card);
    });
}

async function saveSelectedProfile() {
    if (formActionsDisabled()) {
        return;
    }
    const profile = selectedProfile();
    setBusy(true);
    setStatusKey("models.saving");
    try {
        const updated = await requestJson(`/api/live2d-models/${profile.id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: DOM.label.value,
                selection_key: DOM.selection.value,
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
        const created = await requestJson("/api/live2d-models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: cleanedLabel,
                source_model_id: sourceProfile.id,
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
        await requestJson(`/api/live2d-models/${profile.id}/activate`, {
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
        const payload = await requestJson(`/api/live2d-models/${profile.id}`, {
            method: "DELETE",
        });
        state.selectedProfileId = payload.active_live2d_model_id
            || (Array.isArray(payload.models) && payload.models[0] && payload.models[0].id)
            || "a";
        await load({ selectedProfileId: payload.active_live2d_model_id || state.selectedProfileId });
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
    return live2dProfiles().find((item) => item.id === state.selectedProfileId)
        || live2dProfiles()[0]
        || {
            id: "a",
            name: i18n.t("models.newProfileDefault", { count: 1 }),
            selection_key: "",
        };
}

function live2dProfiles() {
    return state.live2dPayload && Array.isArray(state.live2dPayload.models)
        ? state.live2dPayload.models
        : [];
}

function resolveExistingProfileId(profileId, live2dPayload = state.live2dPayload) {
    const normalizedId = String(profileId || "").trim();
    if (!normalizedId) {
        return "";
    }
    const models = live2dPayload && Array.isArray(live2dPayload.models)
        ? live2dPayload.models
        : [];
    return models.some((item) => item.id === normalizedId) ? normalizedId : "";
}

function catalog() {
    return state.live2dPayload && Array.isArray(state.live2dPayload.catalog)
        ? state.live2dPayload.catalog
        : [];
}

function activeProfileId() {
    return state.live2dPayload && state.live2dPayload.active_live2d_model_id || "";
}

function canDeleteSelectedProfile(profile = selectedProfile()) {
    const profileCount = live2dProfiles().length;
    return Boolean(
        profile
        && profile.id
        && profile.id !== activeProfileId()
        && profileCount > 1,
    );
}

function nextProfileLabel() {
    const count = live2dProfiles().length + 1;
    return i18n.t("models.newProfileDefault", { count });
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

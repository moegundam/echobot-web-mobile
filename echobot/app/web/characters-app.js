import { initShellI18n } from "./shell-i18n.js?v=site-public-6";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";

const state = {
    payload: null,
    selectedName: "",
    isCreating: false,
    busy: false,
    statusKey: "characters.loading",
    statusParams: {},
    statusRaw: "",
};

const DOM = {
    list: document.getElementById("character-profile-list"),
    create: document.getElementById("character-profile-create"),
    form: document.getElementById("character-profile-form"),
    title: document.getElementById("character-profile-title"),
    status: document.getElementById("character-profile-status"),
    save: document.getElementById("character-profile-save"),
    remove: document.getElementById("character-profile-delete"),
    name: document.getElementById("character-name"),
    modelProfile: document.getElementById("character-model-profile"),
    prompt: document.getElementById("character-prompt"),
    summary: document.getElementById("character-effective-summary"),
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
    void saveSelectedCharacter();
});
DOM.create.addEventListener("click", () => {
    state.isCreating = true;
    state.selectedName = "";
    setStatusKey("characters.newReady");
    render();
});
DOM.remove.addEventListener("click", () => {
    void deleteSelectedCharacter();
});

void load();

async function load() {
    setBusy(true);
    setStatusKey("characters.loading");
    try {
        state.payload = await requestJson("/api/character-profiles");
        state.isCreating = false;
        const characters = characterList();
        if (!state.selectedName && characters.length > 0) {
            state.selectedName = characters[0].name;
        }
        render();
        setStatusKey("characters.ready");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("characters.loadFailed"));
    } finally {
        setBusy(false);
    }
}

function render() {
    renderCharacterList();
    renderModelProfileOptions();
    renderSelectedCharacter();
}

function renderCharacterList() {
    DOM.list.replaceChildren();
    characterList().forEach((character) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "model-profile-card";
        button.classList.toggle("is-selected", !state.isCreating && character.name === state.selectedName);

        const badge = document.createElement("strong");
        badge.textContent = characterBadge(character.name);
        const label = document.createElement("span");
        label.textContent = character.name;
        const profile = document.createElement("small");
        profile.textContent = profileSummary(character);

        button.append(badge, label, profile);
        button.addEventListener("click", () => {
            state.isCreating = false;
            state.selectedName = character.name;
            render();
        });
        DOM.list.appendChild(button);
    });
}

function renderModelProfileOptions() {
    DOM.modelProfile.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t("characters.useActiveProfile");
    DOM.modelProfile.appendChild(emptyOption);

    modelProfileList().forEach((profile) => {
        const option = document.createElement("option");
        option.value = profile.profile_id;
        option.textContent = `${String(profile.profile_id || "").toUpperCase()} · ${profile.label || profile.profile_id}`;
        DOM.modelProfile.appendChild(option);
    });
}

function renderSelectedCharacter() {
    const character = selectedCharacter();
    const creating = state.isCreating;
    const editable = creating || Boolean(character && character.editable);
    const deletable = Boolean(character && character.deletable);

    DOM.title.textContent = creating
        ? i18n.t("characters.newCharacter")
        : character ? character.name : i18n.t("characters.heading");
    DOM.name.value = creating ? "" : character ? character.name : "";
    DOM.name.disabled = state.busy || !creating;
    DOM.prompt.value = creating ? "" : character ? character.prompt || "" : "";
    DOM.prompt.disabled = state.busy || !editable;
    DOM.modelProfile.value = creating ? "" : character ? character.model_profile_id || "" : "";
    DOM.modelProfile.disabled = state.busy || (!creating && !character);
    DOM.save.disabled = state.busy || (!creating && !character);
    DOM.remove.disabled = state.busy || !deletable || creating;

    renderEffectiveSummary(character);
}

function renderEffectiveSummary(character) {
    DOM.summary.replaceChildren();
    const rows = character
        ? [
            ["characters.effectiveProfile", character.effective_model_profile_id || ""],
            ["models.label", character.model_profile_label || ""],
            ["models.chat", character.chat_model || ""],
            ["models.voice", character.tts_voice || ""],
            ["models.asr", character.asr_model || ""],
            ["models.live2d", character.live2d_selection_key || ""],
        ]
        : [["characters.effectiveProfile", i18n.t("characters.summaryAfterSave")]];

    rows.forEach(([labelKey, value]) => {
        const row = document.createElement("p");
        const label = document.createElement("strong");
        label.textContent = i18n.t(labelKey);
        const text = document.createElement("span");
        text.textContent = value || i18n.t("channels.none");
        row.append(label, document.createTextNode(": "), text);
        DOM.summary.appendChild(row);
    });
}

async function saveSelectedCharacter() {
    const name = DOM.name.value.trim();
    const prompt = DOM.prompt.value.trim();
    const modelProfileId = DOM.modelProfile.value.trim();
    if (state.isCreating && !name) {
        setStatusKey("characters.nameRequired");
        return;
    }
    if (!prompt && (state.isCreating || selectedCharacter()?.editable)) {
        setStatusKey("characters.promptRequired");
        return;
    }

    setBusy(true);
    setStatusKey("characters.saving");
    try {
        if (state.isCreating) {
            const created = await requestJson("/api/character-profiles", {
                method: "POST",
                body: JSON.stringify({
                    name,
                    prompt,
                    model_profile_id: modelProfileId,
                }),
            });
            state.selectedName = created.name;
        } else {
            const selected = selectedCharacter();
            if (!selected) {
                return;
            }
            await requestJson(`/api/character-profiles/${encodeURIComponent(selected.name)}`, {
                method: "PATCH",
                body: JSON.stringify({
                    prompt: selected.editable ? prompt : undefined,
                    model_profile_id: modelProfileId || undefined,
                    clear_model_profile_binding: !modelProfileId,
                }),
            });
        }
        await load();
        setStatusKey("characters.saved");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("characters.saveFailed"));
    } finally {
        setBusy(false);
    }
}

async function deleteSelectedCharacter() {
    const character = selectedCharacter();
    if (!character || !character.deletable) {
        return;
    }
    if (!window.confirm(i18n.t("characters.deleteConfirm", { character: character.name }))) {
        return;
    }

    setBusy(true);
    setStatusKey("characters.deleting");
    try {
        await requestJson(`/api/character-profiles/${encodeURIComponent(character.name)}`, {
            method: "DELETE",
        });
        state.selectedName = "";
        await load();
        setStatusKey("characters.deleted");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("characters.deleteFailed"));
    } finally {
        setBusy(false);
    }
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Accept": "application/json",
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });
    if (!response.ok) {
        throw await responseToError(response);
    }
    return await response.json();
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

function characterList() {
    return state.payload && Array.isArray(state.payload.characters)
        ? state.payload.characters
        : [];
}

function modelProfileList() {
    return state.payload && Array.isArray(state.payload.model_profiles)
        ? state.payload.model_profiles
        : [];
}

function selectedCharacter() {
    if (state.isCreating) {
        return null;
    }
    return characterList().find((character) => character.name === state.selectedName) || null;
}

function characterBadge(name) {
    return String(name || "?")
        .split(/[-_\s]+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toUpperCase() || "?";
}

function profileSummary(character) {
    if (!character) {
        return "";
    }
    if (character.model_profile_id) {
        return i18n.t("characters.boundProfile", {
            profile: character.model_profile_id.toUpperCase(),
        });
    }
    return i18n.t("characters.usesActiveProfile", {
        profile: String(character.effective_model_profile_id || "").toUpperCase(),
    });
}

function setBusy(value) {
    state.busy = Boolean(value);
    renderSelectedCharacter();
}

function setStatusKey(key, params = {}) {
    state.statusKey = key;
    state.statusParams = params;
    state.statusRaw = "";
    refreshStatus();
}

function setRawStatus(message) {
    state.statusRaw = String(message || "");
    refreshStatus();
}

function refreshStatus() {
    DOM.status.textContent = state.statusRaw || i18n.t(state.statusKey, state.statusParams);
}

import { initShellI18n } from "./shell-i18n.js?v=admin-boundary-1";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";

const state = {
    payload: null,
    webConfig: null,
    channelIntegrations: [],
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
    exportPackage: document.getElementById("character-profile-export"),
    remove: document.getElementById("character-profile-delete"),
    name: document.getElementById("character-name"),
    modelProfile: document.getElementById("character-model-profile"),
    llmModel: document.getElementById("character-llm-model"),
    voiceProfile: document.getElementById("character-voice-profile"),
    live2dProfile: document.getElementById("character-live2d-profile"),
    defaultChannelType: document.getElementById("character-default-channel-type"),
    defaultChannelIntegration: document.getElementById("character-default-channel-integration"),
    prompt: document.getElementById("character-prompt"),
    emotionMap: document.getElementById("character-emotion-map"),
    emotionMapAdd: document.getElementById("character-emotion-map-add"),
    expressionOptions: document.getElementById("character-expression-options"),
    motionOptions: document.getElementById("character-motion-options"),
    summary: document.getElementById("character-effective-summary"),
    importPackage: document.getElementById("character-package-import-submit"),
    packageJson: document.getElementById("character-package-json"),
    packageImportName: document.getElementById("character-package-import-name"),
    packageOverwrite: document.getElementById("character-package-overwrite"),
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
DOM.exportPackage.addEventListener("click", () => {
    void exportSelectedCharacter();
});
DOM.emotionMapAdd.addEventListener("click", () => {
    appendEmotionMapRow();
});
DOM.importPackage.addEventListener("click", () => {
    void importCharacterPackage();
});
DOM.defaultChannelIntegration.addEventListener("change", () => {
    syncChannelTypeFromIntegration();
});

void load();

async function load() {
    setBusy(true);
    setStatusKey("characters.loading");
    try {
        const [payload, webConfig, channelIntegrations] = await Promise.all([
            requestJson("/api/character-profiles"),
            requestJson("/api/web/config").catch((error) => {
                console.warn("Unable to load Live2D options for character emotion maps", error);
                return null;
            }),
            requestJson("/api/channel-integrations").catch((error) => {
                console.warn("Unable to load channel integrations for character defaults", error);
                return { integrations: [] };
            }),
        ]);
        state.payload = payload;
        state.webConfig = webConfig;
        state.channelIntegrations = Array.isArray(channelIntegrations.integrations)
            ? channelIntegrations.integrations
            : [];
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
    renderProfileSelectOptions(DOM.modelProfile, "characters.useActiveProfile");
    renderProfileSelectOptions(DOM.llmModel, "characters.useBaseProfile");
    renderProfileSelectOptions(DOM.voiceProfile, "characters.useBaseProfile");
    renderProfileSelectOptions(DOM.live2dProfile, "characters.useBaseProfile");
    renderChannelTypeOptions();
    renderChannelIntegrationOptions();
}

function renderProfileSelectOptions(select, emptyLabelKey) {
    select.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t(emptyLabelKey);
    select.appendChild(emptyOption);

    modelProfileList().forEach((profile) => {
        const option = document.createElement("option");
        option.value = profile.profile_id;
        option.textContent = `${String(profile.profile_id || "").toUpperCase()} · ${profile.label || profile.profile_id}`;
        select.appendChild(option);
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
    DOM.llmModel.value = creating ? "" : character ? character.llm_model_id || "" : "";
    DOM.llmModel.disabled = state.busy || (!creating && !character);
    DOM.voiceProfile.value = creating ? "" : character ? character.voice_profile_id || "" : "";
    DOM.voiceProfile.disabled = state.busy || (!creating && !character);
    DOM.live2dProfile.value = creating ? "" : character ? character.live2d_model_id || "" : "";
    DOM.live2dProfile.disabled = state.busy || (!creating && !character);
    DOM.defaultChannelType.value = creating ? "" : character ? character.default_channel_type || "" : "";
    DOM.defaultChannelType.disabled = state.busy || (!creating && !character);
    DOM.defaultChannelIntegration.value = creating
        ? ""
        : character ? character.default_channel_integration_id || "" : "";
    DOM.defaultChannelIntegration.disabled = state.busy || (!creating && !character);
    DOM.save.disabled = state.busy || (!creating && !character);
    DOM.exportPackage.disabled = state.busy || creating || !character;
    DOM.remove.disabled = state.busy || !deletable || creating;
    DOM.emotionMapAdd.disabled = state.busy || (!creating && !character);
    DOM.importPackage.disabled = state.busy;
    DOM.packageJson.disabled = state.busy;
    DOM.packageImportName.disabled = state.busy;
    DOM.packageOverwrite.disabled = state.busy;

    renderLive2DActionOptions(character);
    renderEmotionMapEditor(character);
    renderEffectiveSummary(character);
}

function renderEffectiveSummary(character) {
    DOM.summary.replaceChildren();
    const rows = character
        ? [
            ["characters.effectiveProfile", character.effective_model_profile_id || ""],
            ["characters.llmModel", character.llm_model_id || character.effective_model_profile_id || ""],
            ["characters.voiceProfile", character.voice_profile_id || character.effective_model_profile_id || ""],
            ["characters.live2dProfile", character.live2d_model_id || character.effective_model_profile_id || ""],
            ["characters.defaultChannelType", character.default_channel_type || ""],
            ["characters.defaultChannelIntegration", character.default_channel_integration_id || ""],
            ["models.label", character.model_profile_label || ""],
            ["models.chat", character.chat_model || ""],
            ["models.voice", character.tts_voice || ""],
            ["models.asr", character.asr_model || ""],
            ["models.live2d", character.live2d_selection_key || ""],
            ["characters.emotionMapCount", i18n.t("characters.emotionMapCountValue", {
                count: String((character.emotion_maps || []).length),
            })],
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
    const llmModelId = DOM.llmModel.value.trim();
    const voiceProfileId = DOM.voiceProfile.value.trim();
    const live2dProfileId = DOM.live2dProfile.value.trim();
    const defaultChannelType = DOM.defaultChannelType.value.trim();
    const defaultChannelIntegrationId = DOM.defaultChannelIntegration.value.trim();
    const emotionMaps = collectEmotionMaps();
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
                    llm_model_id: llmModelId,
                    voice_profile_id: voiceProfileId,
                    live2d_model_id: live2dProfileId,
                    default_channel_type: defaultChannelType,
                    default_channel_integration_id: defaultChannelIntegrationId,
                    emotion_maps: emotionMaps,
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
                    llm_model_id: llmModelId,
                    voice_profile_id: voiceProfileId,
                    live2d_model_id: live2dProfileId,
                    default_channel_type: defaultChannelType,
                    default_channel_integration_id: defaultChannelIntegrationId,
                    clear_model_profile_binding: !modelProfileId,
                    emotion_maps: emotionMaps,
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

async function exportSelectedCharacter() {
    const character = selectedCharacter();
    if (!character) {
        return;
    }

    setBusy(true);
    setStatusKey("characters.exporting");
    try {
        const packagePayload = await requestJson(
            `/api/character-profiles/${encodeURIComponent(character.name)}/package`,
        );
        const packageJson = JSON.stringify(packagePayload, null, 2);
        DOM.packageJson.value = packageJson;
        downloadCharacterPackage(character.name, packageJson);
        setStatusKey("characters.exported");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("characters.exportFailed"));
    } finally {
        setBusy(false);
    }
}

async function importCharacterPackage() {
    const rawJson = DOM.packageJson.value.trim();
    if (!rawJson) {
        setStatusKey("characters.packageJsonRequired");
        return;
    }

    let packagePayload;
    try {
        packagePayload = JSON.parse(rawJson);
    } catch (_error) {
        setStatusKey("characters.packageJsonInvalid");
        return;
    }

    const importName = DOM.packageImportName.value.trim();
    if (importName) {
        packagePayload.import_name = importName;
    }
    packagePayload.overwrite = DOM.packageOverwrite.checked;

    setBusy(true);
    setStatusKey("characters.importing");
    try {
        const imported = await requestJson("/api/character-profiles/package", {
            method: "POST",
            body: JSON.stringify(packagePayload),
        });
        state.selectedName = imported.name;
        state.isCreating = false;
        DOM.packageImportName.value = "";
        DOM.packageOverwrite.checked = false;
        await load();
        setStatusKey("characters.imported");
    } catch (error) {
        console.error(error);
        setRawStatus(error.message || i18n.t("characters.importFailed"));
    } finally {
        setBusy(false);
    }
}

function renderLive2DActionOptions(character) {
    DOM.expressionOptions.replaceChildren();
    DOM.motionOptions.replaceChildren();
    const live2dModel = live2dModelForCharacter(character);
    const expressions = Array.isArray(live2dModel && live2dModel.expressions)
        ? live2dModel.expressions
        : [];
    const motions = Array.isArray(live2dModel && live2dModel.motions)
        ? live2dModel.motions
        : [];

    expressions.forEach((item) => {
        const option = document.createElement("option");
        option.value = String(item.file || item.name || "");
        option.label = String(item.name || item.file || "");
        DOM.expressionOptions.appendChild(option);
    });
    motions.forEach((item) => {
        const option = document.createElement("option");
        option.value = String(item.file || item.name || "");
        option.label = String(item.name || item.file || "");
        DOM.motionOptions.appendChild(option);
    });
}

function renderChannelTypeOptions() {
    DOM.defaultChannelType.replaceChildren();
    const options = [
        ["", i18n.t("characters.noDefaultChannel")],
        ["web", "Web"],
        ["telegram", "Telegram"],
        ["discord", "Discord"],
        ["line", "LINE"],
        ["whatsapp", "WhatsApp"],
        ["qq", "QQ"],
    ];
    const existingTypes = new Set(options.map(([value]) => value));
    channelIntegrationList().forEach((integration) => {
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
        DOM.defaultChannelType.appendChild(option);
    });
}

function renderChannelIntegrationOptions() {
    DOM.defaultChannelIntegration.replaceChildren();
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = i18n.t("characters.noDefaultIntegration");
    DOM.defaultChannelIntegration.appendChild(emptyOption);

    channelIntegrationList().forEach((integration) => {
        const option = document.createElement("option");
        option.value = String(integration.id || "").trim();
        option.textContent = channelLabel(integration);
        DOM.defaultChannelIntegration.appendChild(option);
    });
}

function syncChannelTypeFromIntegration() {
    const integrationId = DOM.defaultChannelIntegration.value.trim();
    const integration = channelIntegrationList()
        .find((item) => String(item.id || "") === integrationId);
    if (!integration) {
        return;
    }
    const integrationType = String(integration.type || integration.id || "").trim();
    if (integrationType) {
        DOM.defaultChannelType.value = integrationType;
    }
}

function renderEmotionMapEditor(character) {
    DOM.emotionMap.replaceChildren();
    const maps = character && Array.isArray(character.emotion_maps)
        ? character.emotion_maps
        : [];
    if (maps.length === 0) {
        const empty = document.createElement("p");
        empty.className = "model-role-binding-empty";
        empty.textContent = i18n.t("characters.emotionMapEmpty");
        DOM.emotionMap.appendChild(empty);
        return;
    }
    maps.forEach((item) => {
        appendEmotionMapRow(item);
    });
}

function appendEmotionMapRow(item = {}) {
    const empty = DOM.emotionMap.querySelector(".model-role-binding-empty");
    if (empty) {
        empty.remove();
    }

    const row = document.createElement("article");
    row.className = "character-emotion-map-row";
    row.dataset.emotionMapRow = "true";

    const emotionLabel = emotionInputField(
        "characters.emotionLabel",
        "characters.emotionPlaceholder",
        "emotion",
        item.emotion,
    );
    const expressionLabel = emotionInputField(
        "characters.expressionLabel",
        "characters.expressionPlaceholder",
        "expression",
        item.expression,
        "character-expression-options",
    );
    const motionLabel = emotionInputField(
        "characters.motionLabel",
        "characters.motionPlaceholder",
        "motion",
        item.motion,
        "character-motion-options",
    );

    const actions = document.createElement("div");
    actions.className = "character-emotion-map-actions";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = i18n.t("characters.emotionMapRemove");
    remove.addEventListener("click", () => {
        row.remove();
        if (!DOM.emotionMap.querySelector("[data-emotion-map-row]")) {
            renderEmotionMapEditor({ emotion_maps: [] });
        }
    });
    actions.appendChild(remove);
    row.append(emotionLabel, expressionLabel, motionLabel, actions);
    DOM.emotionMap.appendChild(row);
}

function emotionInputField(labelKey, placeholderKey, fieldName, value = "", listId = "") {
    const label = document.createElement("label");
    const labelText = document.createElement("span");
    labelText.textContent = i18n.t(labelKey);
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 256;
    input.autocomplete = "off";
    input.dataset.emotionMapField = fieldName;
    input.placeholder = i18n.t(placeholderKey);
    input.value = String(value || "");
    input.disabled = state.busy;
    if (listId) {
        input.setAttribute("list", listId);
    }
    label.append(labelText, input);
    return label;
}

function collectEmotionMaps() {
    return Array.from(DOM.emotionMap.querySelectorAll("[data-emotion-map-row]"))
        .map((row) => ({
            emotion: fieldValue(row, "emotion"),
            expression: fieldValue(row, "expression"),
            motion: fieldValue(row, "motion"),
        }))
        .filter((item) => item.emotion || item.expression || item.motion);
}

function fieldValue(row, fieldName) {
    const input = row.querySelector(`[data-emotion-map-field="${fieldName}"]`);
    return String((input && input.value) || "").trim();
}

function downloadCharacterPackage(characterName, packageJson) {
    const blob = new Blob([packageJson, "\n"], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${safeFileName(characterName)}.echobot-character.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

function safeFileName(value) {
    return String(value || "character")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, "-")
        .replace(/^-+|-+$/g, "")
        || "character";
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

function channelIntegrationList() {
    return Array.isArray(state.channelIntegrations)
        ? state.channelIntegrations
        : [];
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

function live2dModelForCharacter(character) {
    const live2d = state.webConfig && state.webConfig.live2d;
    const models = Array.isArray(live2d && live2d.models) ? live2d.models : [];
    const selectionKey = String(character && character.live2d_selection_key || "");
    if (!selectionKey) {
        return models.find((item) => item && item.model_url) || live2d || null;
    }
    return models.find((item) => {
        if (!item) {
            return false;
        }
        return item.selection_key === selectionKey || item.model_url === selectionKey;
    }) || null;
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
    if (character.llm_model_id || character.voice_profile_id || character.live2d_model_id) {
        return i18n.t("characters.splitProfileSummary");
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

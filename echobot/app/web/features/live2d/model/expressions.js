export function normalizeExpressionItem(expressionItem) {
    if (!expressionItem || typeof expressionItem !== "object") {
        return null;
    }
    const file = String(expressionItem.file || "");
    const url = String(expressionItem.url || "");
    if (!file || !url) {
        return null;
    }
    return {
        name: String(expressionItem.name || file),
        file: file,
        url: url,
    };
}

export function normalizeMotionItem(motionItem) {
    if (!motionItem || typeof motionItem !== "object") {
        return null;
    }
    const file = String(motionItem.file || "");
    const group = String(motionItem.group || "");
    const index = Number.isInteger(motionItem.index) ? motionItem.index : 0;
    if (!file || !group) {
        return null;
    }
    return {
        name: String(motionItem.name || file),
        file: file,
        group: group,
        index: index,
    };
}

export function normalizeHotkeyItem(hotkeyItem) {
    if (!hotkeyItem || typeof hotkeyItem !== "object") {
        return null;
    }
    return {
        hotkey_id: String(hotkeyItem.hotkey_id || ""),
        name: String(hotkeyItem.name || hotkeyItem.action || "Hotkey"),
        action: String(hotkeyItem.action || ""),
        file: String(hotkeyItem.file || ""),
        supported: Boolean(hotkeyItem.supported),
    };
}

export function normalizeExpressionBlend(blend) {
    const normalizedBlend = String(blend || "").trim().toLowerCase();
    if (normalizedBlend === "add") {
        return "Add";
    }
    if (normalizedBlend === "multiply") {
        return "Multiply";
    }
    return "Set";
}

export function parseExpressionDefinition(payload, expressionItem) {
    const parameters = Array.isArray(payload && payload.Parameters)
        ? payload.Parameters
            .filter((item) => item && typeof item === "object")
            .map((item) => ({
                id: String(item.Id || ""),
                value: typeof item.Value === "number" ? item.Value : 0,
                blend: normalizeExpressionBlend(item.Blend),
            }))
            .filter((item) => item.id)
        : [];

    return {
        name: expressionItem.name,
        file: expressionItem.file,
        parameters: parameters,
    };
}

export function createLive2DExpressionController({
    live2dState,
    defaultLipSyncIds,
    normalizeSelectionKey,
    selectionKeyFromConfig,
    resolveActionSelectionKey,
    assertSelectionReady,
    getSelectionRuntimeState,
    t,
}) {
    function attachLipSyncHook(model, live2dConfig) {
        detachLipSyncHook();

        const internalModel = model.internalModel;
        if (!internalModel || typeof internalModel.on !== "function") {
            return;
        }

        live2dState.lipSyncHook = function () {
            applyMouthValue(live2dConfig, live2dState.currentMouthValue);
            applyActiveExpressions();
        };
        internalModel.on("beforeModelUpdate", live2dState.lipSyncHook);
        live2dState.live2dInternalModel = internalModel;
    }

    function detachLipSyncHook() {
        if (
            live2dState.live2dInternalModel
            && live2dState.lipSyncHook
            && typeof live2dState.live2dInternalModel.off === "function"
        ) {
            live2dState.live2dInternalModel.off("beforeModelUpdate", live2dState.lipSyncHook);
        }

        live2dState.live2dInternalModel = null;
        live2dState.lipSyncHook = null;
    }

    function applyMouthValue(live2dConfig, value) {
        if (!live2dConfig || !live2dState.live2dModel || !live2dState.live2dModel.internalModel) {
            return;
        }

        const coreModel = live2dState.live2dModel.internalModel.coreModel;
        if (!coreModel || typeof coreModel.setParameterValueById !== "function") {
            return;
        }

        const lipSyncIds = (live2dConfig.lip_sync_parameter_ids || []).length > 0
            ? live2dConfig.lip_sync_parameter_ids
            : defaultLipSyncIds;

        lipSyncIds.forEach((parameterId) => {
            try {
                coreModel.setParameterValueById(parameterId, value);
            } catch (error) {
                console.warn(`Failed to update lip sync parameter ${parameterId}`, error);
            }
        });

        if (live2dConfig.mouth_form_parameter_id) {
            try {
                coreModel.setParameterValueById(live2dConfig.mouth_form_parameter_id, 0);
            } catch (error) {
                console.warn("Failed to reset mouth form parameter", error);
            }
        }
    }

    function applyActiveExpressions() {
        const model = live2dState.live2dModel;
        const internalModel = model && model.internalModel;
        const coreModel = internalModel && internalModel.coreModel;
        if (
            !coreModel
            || typeof coreModel.setParameterValueById !== "function"
            || live2dState.activeExpressionMap.size === 0
        ) {
            return;
        }

        live2dState.activeExpressionMap.forEach((expressionDefinition) => {
            expressionDefinition.parameters.forEach((parameter) => {
                try {
                    if (parameter.blend === "Add" && typeof coreModel.addParameterValueById === "function") {
                        coreModel.addParameterValueById(parameter.id, parameter.value);
                        return;
                    }
                    if (
                        parameter.blend === "Multiply"
                        && typeof coreModel.multiplyParameterValueById === "function"
                    ) {
                        coreModel.multiplyParameterValueById(parameter.id, parameter.value);
                        return;
                    }
                    coreModel.setParameterValueById(parameter.id, parameter.value);
                } catch (error) {
                    console.warn(`Failed to apply Live2D expression parameter ${parameter.id}`, error);
                }
            });
        });
    }

    async function toggleExpression(expressionItem, selectionKey = "") {
        const normalizedSelectionKey = resolveActionSelectionKey(selectionKey);
        const normalizedItem = normalizeExpressionItem(expressionItem);
        if (!normalizedItem) {
            throw new Error(t("console.live2dInvalidExpression"));
        }
        assertSelectionReady(normalizedSelectionKey);

        if (live2dState.activeExpressionMap.has(normalizedItem.file)) {
            live2dState.activeExpressionMap.delete(normalizedItem.file);
            syncActiveExpressionFiles();
            return {
                active: false,
                name: normalizedItem.name,
                file: normalizedItem.file,
            };
        }

        const expressionDefinition = await loadExpressionDefinition(
            normalizedItem,
            normalizedSelectionKey,
        );
        assertSelectionReady(normalizedSelectionKey);
        live2dState.activeExpressionMap.set(normalizedItem.file, expressionDefinition);
        syncActiveExpressionFiles();
        return {
            active: true,
            name: normalizedItem.name,
            file: normalizedItem.file,
        };
    }

    function clearActiveExpressions() {
        live2dState.activeExpressionMap.clear();
        syncActiveExpressionFiles();
    }

    async function playMotion(motionItem, selectionKey = "") {
        const normalizedSelectionKey = resolveActionSelectionKey(selectionKey);
        const model = live2dState.live2dModel;
        const normalizedItem = normalizeMotionItem(motionItem);
        if (!model || !normalizedItem) {
            throw new Error(t("console.live2dInvalidMotion"));
        }
        assertSelectionReady(normalizedSelectionKey);
        if (typeof model.motion !== "function") {
            throw new Error(t("console.live2dMotionUnsupported"));
        }

        await model.motion(normalizedItem.group, normalizedItem.index);
        return {
            name: normalizedItem.name,
            file: normalizedItem.file,
        };
    }

    async function triggerHotkey(hotkeyItem, live2dConfig) {
        const selectionKey = selectionKeyFromConfig(live2dConfig);
        const normalizedHotkey = normalizeHotkeyItem(hotkeyItem);
        if (!normalizedHotkey || !normalizedHotkey.supported) {
            throw new Error(t("console.live2dUnsupportedHotkey"));
        }

        if (normalizedHotkey.action === "ToggleExpression") {
            const expressionItem = (live2dConfig && live2dConfig.expressions || []).find(
                (item) => item.file === normalizedHotkey.file,
            );
            if (!expressionItem) {
                throw new Error(t("console.live2dExpressionNotFound", { file: normalizedHotkey.file }));
            }
            const result = await toggleExpression(expressionItem, selectionKey);
            return {
                hotkey: normalizedHotkey,
                result: result,
            };
        }

        if (normalizedHotkey.action === "TriggerAnimation") {
            const motionItem = (live2dConfig && live2dConfig.motions || []).find(
                (item) => item.file === normalizedHotkey.file,
            );
            if (!motionItem) {
                throw new Error(t("console.live2dMotionNotFound", { file: normalizedHotkey.file }));
            }
            const result = await playMotion(motionItem, selectionKey);
            return {
                hotkey: normalizedHotkey,
                result: result,
            };
        }

        if (normalizedHotkey.action === "RemoveAllExpressions") {
            assertSelectionReady(selectionKey);
            clearActiveExpressions();
            return {
                hotkey: normalizedHotkey,
                result: {
                    cleared: true,
                },
            };
        }

        throw new Error(t("console.live2dUnsupportedHotkeyAction", { action: normalizedHotkey.action }));
    }

    function isExpressionActive(selectionKey, file) {
        if (!getSelectionRuntimeState(selectionKey).canInteract) {
            return false;
        }

        return live2dState.activeExpressionMap.has(String(file || ""));
    }

    function syncActiveExpressionFiles() {
        live2dState.activeExpressionFiles = Array.from(live2dState.activeExpressionMap.keys());
    }

    async function loadExpressionDefinition(expressionItem, selectionKey) {
        assertSelectionReady(selectionKey);

        const cacheKey = `${normalizeSelectionKey(selectionKey)}::${expressionItem.url}`;
        if (live2dState.expressionDataCache.has(cacheKey)) {
            return live2dState.expressionDataCache.get(cacheKey);
        }

        const response = await fetch(expressionItem.url, {
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(t("console.live2dExpressionLoadFailed", { name: expressionItem.name }));
        }

        const payload = await response.json();
        assertSelectionReady(selectionKey);
        const expressionDefinition = parseExpressionDefinition(payload, expressionItem);
        live2dState.expressionDataCache.set(cacheKey, expressionDefinition);
        return expressionDefinition;
    }

    return {
        applyActiveExpressions,
        applyMouthValue,
        attachLipSyncHook,
        clearActiveExpressions,
        detachLipSyncHook,
        isExpressionActive,
        playMotion,
        toggleExpression,
        triggerHotkey,
    };
}

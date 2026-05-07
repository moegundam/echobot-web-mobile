import { DOM } from "../../core/dom.js";
import { appState } from "../../core/store.js";
import { readJson, removeStoredValue, writeJson } from "../../core/storage.js";
import { createStageBackgroundController } from "./backgrounds.js?v=stage-background-1";
import { createLive2DConfigController } from "./config.js?v=site-public-6";
import { createLive2DControlsController } from "./controls.js?v=site-public-6";
import { createStageEffectsController } from "./effects.js?v=site-public-6";
import { createLive2DModelController } from "./model.js?v=site-public-6";
import { createLive2DSceneController } from "./scene.js";

export function createLive2DModule(deps) {
    const {
        clamp,
        requestJson,
        roundTo,
        responseToError,
        setRunStatus,
        t = (key) => key,
    } = deps;

    function setStageMessage(text) {
        const message = String(text || "").trim();
        if (!DOM.stageMessage) {
            return;
        }

        delete DOM.stageMessage.dataset.i18nKey;
        DOM.stageMessage.textContent = message;
        DOM.stageMessage.hidden = message === "";
    }

    let sceneController = null;

    const effectsController = createStageEffectsController({
        clamp,
        roundTo,
        setRunStatus,
        t,
        applyStageLightingVars(...args) {
            sceneController?.applyStageLightingVars(...args);
        },
        updateStageAtmosphereFrame(...args) {
            sceneController?.updateStageAtmosphereFrame(...args);
        },
    });

    const backgroundController = createStageBackgroundController({
        clamp,
        roundTo,
        responseToError,
        setRunStatus,
        t,
        applyStageEffectsToRuntime(...args) {
            effectsController.applyStageEffectsToRuntime(...args);
        },
    });

    const modelController = createLive2DModelController({
        clamp,
        roundTo,
        readJson,
        removeStoredValue,
        setStageMessage,
        t,
        writeJson,
    });

    const controlsController = createLive2DControlsController({
        getSelectionRuntimeState(...args) {
            return modelController.getSelectionRuntimeState(...args);
        },
        isExpressionActive(...args) {
            return modelController.isExpressionActive(...args);
        },
        playMotion(...args) {
            return modelController.playMotion(...args);
        },
        requestJson,
        setRunStatus,
        t,
        toggleExpression(...args) {
            return modelController.toggleExpression(...args);
        },
        triggerHotkey(...args) {
            return modelController.triggerHotkey(...args);
        },
    });

    sceneController = createLive2DSceneController({
        clamp,
        roundTo,
        applyStageEffectsSettings(...args) {
            effectsController.applyStageEffectsSettings(...args);
        },
        applyStageBackgroundTransform(...args) {
            backgroundController.applyStageBackgroundTransform(...args);
        },
        currentStageBackgroundOption(...args) {
            return backgroundController.currentStageBackgroundOption(...args);
        },
        refreshLive2DFocusFromLastPointer(...args) {
            modelController.refreshLive2DFocusFromLastPointer(...args);
        },
        syncPixiStageBackground(...args) {
            return backgroundController.syncPixiStageBackground(...args);
        },
    });

    const configController = createLive2DConfigController({
        responseToError,
        setRunStatus,
        setStageMessage,
        t,
        applyLive2DMouseFollowSetting(...args) {
            modelController.applyLive2DMouseFollowSetting(...args);
        },
        applyStageBackgroundByKey(...args) {
            backgroundController.applyStageBackgroundByKey(...args);
        },
        applyStageEffectsSettings(...args) {
            effectsController.applyStageEffectsSettings(...args);
        },
        buildStageConfig(...args) {
            return backgroundController.normalizeStageConfig(...args);
        },
        loadLive2DModel(...args) {
            return modelController.loadLive2DModel(...args);
        },
        loadSavedStageEffectsSettings(...args) {
            return effectsController.loadSavedStageEffectsSettings(...args);
        },
        resetLive2DHotkeyState(...args) {
            return controlsController.resetHotkeyState(...args);
        },
        renderLive2DControls(...args) {
            return controlsController.renderLive2DControls(...args);
        },
        renderStageBackgroundOptions(...args) {
            backgroundController.renderStageBackgroundOptions(...args);
        },
        resolveInitialStageBackgroundKey(...args) {
            return backgroundController.resolveInitialStageBackgroundKey(...args);
        },
    });

    return {
        applyConfigToUI: configController.applyConfigToUI,
        applyLive2DMouseFollowSetting: modelController.applyLive2DMouseFollowSetting,
        applyMouthValue: modelController.applyMouthValue,
        handleLive2DDirectoryUpload: configController.handleLive2DDirectoryUpload,
        handleLive2DModelChange: configController.handleLive2DModelChange,
        handleLive2DControlsClick: controlsController.handleControlsClick,
        handleLive2DControlsFocusIn: controlsController.handleControlsFocusIn,
        handleLive2DControlsFocusOut: controlsController.handleControlsFocusOut,
        handleLive2DControlsInput: controlsController.handleControlsInput,
        handleLive2DControlsKeyDown: controlsController.handleControlsKeyDown,
        handleLive2DHotkeyKeyDown: controlsController.handleWindowKeyDown,
        handleLive2DHotkeyKeyUp: controlsController.handleWindowKeyUp,
        handleLive2DHotkeyWindowBlur: controlsController.handleWindowBlur,
        handleHotkeysToggle: configController.handleHotkeysToggle,
        handleMouseFollowToggle: configController.handleMouseFollowToggle,
        handleStageBackgroundChange: backgroundController.handleStageBackgroundChange,
        handleStageBackgroundReset: backgroundController.handleStageBackgroundReset,
        handleStageBackgroundTransformInput: backgroundController.handleStageBackgroundTransformInput,
        handleStageBackgroundTransformReset: backgroundController.handleStageBackgroundTransformReset,
        handleStageBackgroundUpload: backgroundController.handleStageBackgroundUpload,
        currentStageBackgroundOverride: backgroundController.currentStageBackgroundOverride,
        handleStageEffectsInput: effectsController.handleStageEffectsInput,
        handleStageEffectsReset: effectsController.handleStageEffectsReset,
        handleStageWheel: modelController.handleStageWheel,
        initializePixiApplication: sceneController.initializePixiApplication,
        loadLive2DModel: modelController.loadLive2DModel,
        renderLive2DControls: controlsController.renderLive2DControls,
        refreshLocalizedText() {
            configController.refreshLocalizedText?.();
            backgroundController.refreshLocalizedText?.();
            effectsController.refreshLocalizedText?.();
            controlsController.renderLive2DControls(appState.config && appState.config.live2d);
        },
        resetLive2DViewToDefault: modelController.resetLive2DViewToDefault,
        setStageMessage,
    };
}

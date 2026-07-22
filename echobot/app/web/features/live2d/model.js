import { DEFAULT_LIP_SYNC_IDS, appState, live2dState } from "../../core/store.js";
import { createLive2DFocusController } from "./model/focus.js";
import {
    createLive2DExpressionController,
} from "./model/expressions.js";
import {
    LIVE2D_MAX_SCALE,
    LIVE2D_MIN_SCALE,
    buildTransformSnapshot,
    calculateDefaultTransform,
    calculateResizedTransform,
    canRestoreSavedTransform,
    measureLive2DBaseSize,
    normalizeSelectionKey,
    selectionKeyFromConfig,
    shouldIgnoreStageWheel,
} from "./model/transform.js";

const LIVE2D_TRANSFORM_SAVE_DELAY_MS = 140;

export function createLive2DModelController(deps) {
    const {
        clamp,
        roundTo,
        readJson,
        removeStoredValue,
        setStageMessage,
        t = (key) => key,
        writeJson,
    } = deps;

    let transformSaveTimerId = 0;
    let pendingTransformSnapshot = null;

    const focusController = createLive2DFocusController({
        clamp,
        live2dState,
    });

    const expressionController = createLive2DExpressionController({
        assertSelectionReady,
        defaultLipSyncIds: DEFAULT_LIP_SYNC_IDS,
        getSelectionRuntimeState,
        live2dState,
        normalizeSelectionKey,
        resolveActionSelectionKey,
        selectionKeyFromConfig,
        t,
    });

    function markSelectionLoading(selectionKey) {
        live2dState.live2dLoading = true;
        live2dState.live2dPendingSelectionKey = normalizeSelectionKey(selectionKey);
        suspendCurrentModelInteractions();
    }

    function finishSelectionLoad(selectionKey) {
        const normalizedSelectionKey = normalizeSelectionKey(selectionKey);
        live2dState.live2dLoading = false;
        live2dState.live2dPendingSelectionKey = normalizedSelectionKey;
        live2dState.live2dActiveSelectionKey = normalizedSelectionKey;
    }

    function restoreSelectionState() {
        live2dState.live2dLoading = false;
        live2dState.live2dPendingSelectionKey = live2dState.live2dActiveSelectionKey;
        resumeCurrentModelInteractions();
    }

    function clearSelectionState() {
        live2dState.live2dLoading = false;
        live2dState.live2dPendingSelectionKey = "";
        live2dState.live2dActiveSelectionKey = "";
    }

    function getSelectionRuntimeState(selectionKey) {
        const normalizedSelectionKey = normalizeSelectionKey(selectionKey);
        const activeSelectionKey = live2dState.live2dActiveSelectionKey;
        const pendingSelectionKey = live2dState.live2dPendingSelectionKey;
        const hasModel = Boolean(live2dState.live2dModel);
        const isActiveSelection = Boolean(
            normalizedSelectionKey
            && normalizedSelectionKey === activeSelectionKey,
        );
        const isPendingSelection = Boolean(
            normalizedSelectionKey
            && normalizedSelectionKey === pendingSelectionKey,
        );

        return {
            isLoading: live2dState.live2dLoading,
            hasModel: hasModel,
            activeSelectionKey: activeSelectionKey,
            pendingSelectionKey: pendingSelectionKey,
            isActiveSelection: isActiveSelection,
            isPendingSelection: isPendingSelection,
            canInteract: Boolean(
                hasModel
                && !live2dState.live2dLoading
                && isActiveSelection,
            ),
        };
    }

    function resolveActionSelectionKey(selectionKey) {
        return normalizeSelectionKey(selectionKey)
            || selectionKeyFromConfig(appState.config && appState.config.live2d);
    }

    function assertSelectionReady(selectionKey) {
        if (!getSelectionRuntimeState(selectionKey).canInteract) {
            throw new Error(t("console.live2dRuntimeNotReady"));
        }
    }

    async function loadLive2DModel(live2dConfig) {
        const loadToken = nextLive2DLoadToken();
        const selectionKey = selectionKeyFromConfig(live2dConfig);
        markSelectionLoading(selectionKey);
        if (!live2dConfig.available || !live2dConfig.model_url) {
            disposeCurrentLive2DModel();
            clearSelectionState();
            setStageMessage(t("console.live2dModelMissing"));
            return false;
        }

        setStageMessage(t("console.live2dLoading"));

        try {
            const model = await window.PIXI.live2d.Live2DModel.from(live2dConfig.model_url, {
                autoInteract: false,
            });
            if (loadToken !== live2dState.live2dLoadToken) {
                destroyLive2DModel(model);
                return false;
            }

            disposeCurrentLive2DModel();
            live2dState.live2dModel = model;
            if (live2dState.live2dCharacterLayer) {
                live2dState.live2dCharacterLayer.addChild(model);
            } else {
                live2dState.live2dStage.addChild(model);
            }

            model.anchor.set(0.5, 0.5);
            model.cursor = "grab";
            model.interactive = true;

            applyLive2DMouseFollowSetting();
            bindLive2DDrag(model);
            expressionController.attachLipSyncHook(model, live2dConfig);
            resetLive2DView();
            finishSelectionLoad(selectionKey);

            setStageMessage("");
            return true;
        } catch (error) {
            console.error(error);
            if (loadToken === live2dState.live2dLoadToken) {
                restoreSelectionState();
                setStageMessage(t("console.live2dModelLoadFailedWithError", { error: error.message || error }));
            }
            throw new Error(t("console.live2dModelLoadFailedWithError", { error: error.message || error }));
        }
    }

    function nextLive2DLoadToken() {
        live2dState.live2dLoadToken += 1;
        return live2dState.live2dLoadToken;
    }

    function suspendCurrentModelInteractions() {
        flushLive2DTransformPersist();
        unbindLive2DDrag();
        focusController.unbind();

        if (!live2dState.live2dModel) {
            return;
        }

        live2dState.live2dModel.interactive = false;
        live2dState.live2dModel.cursor = "wait";
    }

    function resumeCurrentModelInteractions() {
        const model = live2dState.live2dModel;
        if (!model) {
            return;
        }

        model.interactive = true;
        model.cursor = "grab";
        applyLive2DMouseFollowSetting();
        bindLive2DDrag(model);
    }

    function bindLive2DDrag(model) {
        unbindLive2DDrag();

        const pointerDown = (event) => {
            const point = event.data.getLocalPosition(live2dState.live2dStage);
            live2dState.dragging = true;
            live2dState.dragPointerId = event.data.pointerId;
            live2dState.dragOffsetX = model.x - point.x;
            live2dState.dragOffsetY = model.y - point.y;
            model.cursor = "grabbing";
        };

        const pointerMove = (event) => {
            if (!live2dState.dragging || event.data.pointerId !== live2dState.dragPointerId) {
                return;
            }

            const point = event.data.getLocalPosition(live2dState.live2dStage);
            model.x = point.x + live2dState.dragOffsetX;
            model.y = point.y + live2dState.dragOffsetY;
            focusController.refreshFromLastPointer();
            scheduleLive2DTransformPersist();
        };

        const stopDragging = () => {
            if (!live2dState.dragging) {
                return;
            }

            live2dState.dragging = false;
            live2dState.dragPointerId = null;
            model.cursor = "grab";
            scheduleLive2DTransformPersist({ immediate: true });
        };

        model.on("pointerdown", pointerDown);
        live2dState.live2dStage.on("pointermove", pointerMove);
        live2dState.live2dStage.on("pointerup", stopDragging);
        live2dState.live2dStage.on("pointerupoutside", stopDragging);
        live2dState.live2dStage.on("pointerleave", stopDragging);

        live2dState.live2dDragModel = model;
        live2dState.live2dDragHandlers = {
            pointerDown: pointerDown,
            pointerMove: pointerMove,
            stopDragging: stopDragging,
        };
    }

    function unbindLive2DDrag() {
        if (!live2dState.live2dDragHandlers || !live2dState.live2dStage) {
            return;
        }

        if (live2dState.live2dDragModel && typeof live2dState.live2dDragModel.off === "function") {
            live2dState.live2dDragModel.off("pointerdown", live2dState.live2dDragHandlers.pointerDown);
        }

        live2dState.live2dStage.off("pointermove", live2dState.live2dDragHandlers.pointerMove);
        live2dState.live2dStage.off("pointerup", live2dState.live2dDragHandlers.stopDragging);
        live2dState.live2dStage.off("pointerupoutside", live2dState.live2dDragHandlers.stopDragging);
        live2dState.live2dStage.off("pointerleave", live2dState.live2dDragHandlers.stopDragging);

        live2dState.live2dDragModel = null;
        live2dState.live2dDragHandlers = null;
    }

    function applyLive2DMouseFollowSetting() {
        focusController.applyMouseFollowSetting();
    }

    function disposeCurrentLive2DModel() {
        unbindLive2DDrag();
        focusController.unbind();
        expressionController.detachLipSyncHook();
        expressionController.clearActiveExpressions();

        if (live2dState.live2dCharacterLayer) {
            live2dState.live2dCharacterLayer.removeChildren();
        } else if (live2dState.live2dStage) {
            live2dState.live2dStage.removeChildren();
        }

        if (live2dState.live2dModel) {
            destroyLive2DModel(live2dState.live2dModel);
        }

        live2dState.live2dModel = null;
        live2dState.live2dInternalModel = null;
        live2dState.dragging = false;
        live2dState.dragPointerId = null;
    }

    function destroyLive2DModel(model) {
        if (!model || typeof model.destroy !== "function") {
            return;
        }

        try {
            model.destroy({
                children: true,
            });
        } catch (error) {
            console.warn("Failed to destroy Live2D model", error);
        }
    }

    function handleStageWheel(event) {
        if (live2dState.live2dLoading || !live2dState.live2dModel) {
            return;
        }

        if (shouldIgnoreStageWheel(event)) {
            return;
        }

        event.preventDefault();
        const scaleStep = event.deltaY < 0 ? 1.06 : 0.94;
        const nextScale = clamp(
            live2dState.live2dModel.scale.x * scaleStep,
            LIVE2D_MIN_SCALE,
            LIVE2D_MAX_SCALE,
        );
        live2dState.live2dModel.scale.set(nextScale);
        focusController.refreshFromLastPointer();
        scheduleLive2DTransformPersist();
    }

    function resetLive2DView() {
        const model = live2dState.live2dModel;
        if (!model || !live2dState.pixiApp) {
            return;
        }

        const savedTransform = loadSavedLive2DTransform();
        if (savedTransform) {
            model.position.set(savedTransform.x, savedTransform.y);
            model.scale.set(savedTransform.scale);
            focusController.refreshFromLastPointer();
            return;
        }

        applyDefaultLive2DTransform(model);
        focusController.refreshFromLastPointer();
        scheduleLive2DTransformPersist({ immediate: true });
    }

    function resetLive2DViewToDefault() {
        if (live2dState.live2dLoading) {
            return;
        }

        const model = live2dState.live2dModel;
        if (!model || !live2dState.pixiApp) {
            return;
        }

        clearSavedLive2DTransform();
        applyDefaultLive2DTransform(model);
        focusController.refreshFromLastPointer();
        scheduleLive2DTransformPersist({ immediate: true });
    }

    function applyDefaultLive2DTransform(model) {
        const stageWidth = live2dState.pixiApp.screen.width;
        const stageHeight = live2dState.pixiApp.screen.height;
        const transform = calculateDefaultTransform({
            baseSize: measureLive2DBaseSize(model),
            stageHeight: stageHeight,
            stageWidth: stageWidth,
        });
        model.scale.set(transform.scale);
        model.position.set(transform.x, transform.y);
    }

    function reframeLive2DViewForResize(previousStageSize) {
        const model = live2dState.live2dModel;
        const app = live2dState.pixiApp;
        if (!model || !app || !previousStageSize) {
            return;
        }

        const previousWidth = Number(previousStageSize.width);
        const previousHeight = Number(previousStageSize.height);
        const transform = calculateResizedTransform({
            clamp,
            currentStageSize: app.screen,
            modelScale: model.scale.x,
            modelX: model.x,
            modelY: model.y,
            normalizedX: model.x / previousWidth,
            normalizedY: model.y / previousHeight,
            previousStageSize: previousStageSize,
        });
        if (!transform) {
            return;
        }

        model.position.set(transform.x, transform.y);
        model.scale.set(transform.scale);
        focusController.refreshFromLastPointer();
        scheduleLive2DTransformPersist();
    }

    function scheduleLive2DTransformPersist(options = {}) {
        pendingTransformSnapshot = buildLive2DTransformSnapshot();
        if (!pendingTransformSnapshot) {
            return;
        }

        if (transformSaveTimerId) {
            window.clearTimeout(transformSaveTimerId);
            transformSaveTimerId = 0;
        }

        if (options.immediate) {
            flushLive2DTransformPersist();
            return;
        }

        transformSaveTimerId = window.setTimeout(() => {
            transformSaveTimerId = 0;
            flushLive2DTransformPersist();
        }, LIVE2D_TRANSFORM_SAVE_DELAY_MS);
    }

    function flushLive2DTransformPersist() {
        if (transformSaveTimerId) {
            window.clearTimeout(transformSaveTimerId);
            transformSaveTimerId = 0;
        }

        if (!pendingTransformSnapshot) {
            return;
        }

        writeJson(pendingTransformSnapshot.storageKey, pendingTransformSnapshot.transform);
        pendingTransformSnapshot = null;
    }

    function buildLive2DTransformSnapshot() {
        const model = live2dState.live2dModel;
        if (!model || !live2dState.pixiApp) {
            return null;
        }

        return buildTransformSnapshot({
            model: model,
            roundTo: roundTo,
            stageSize: live2dState.pixiApp.screen,
            storageKey: live2dStorageKey(),
        });
    }

    function loadSavedLive2DTransform() {
        const payload = readJson(live2dStorageKey());
        if (
            payload
            && typeof payload.x === "number"
            && typeof payload.y === "number"
            && typeof payload.scale === "number"
            && canRestoreSavedTransform(payload, live2dState.pixiApp && live2dState.pixiApp.screen)
        ) {
            return payload;
        }

        return null;
    }

    function clearSavedLive2DTransform() {
        removeStoredValue(live2dStorageKey());
    }

    function live2dStorageKey() {
        const selectionKey = appState.config && appState.config.live2d
            ? (appState.config.live2d.selection_key || appState.config.live2d.model_url)
            : "default";
        return `echobot.web.live2d.${selectionKey}`;
    }

    return {
        applyLive2DMouseFollowSetting,
        applyMouthValue: expressionController.applyMouthValue,
        clearActiveExpressions: expressionController.clearActiveExpressions,
        getSelectionRuntimeState,
        handleStageWheel,
        loadLive2DModel,
        isExpressionActive: expressionController.isExpressionActive,
        playMotion: expressionController.playMotion,
        reframeLive2DViewForResize,
        refreshLive2DFocusFromLastPointer: focusController.refreshFromLastPointer,
        resetLive2DViewToDefault,
        toggleExpression: expressionController.toggleExpression,
        triggerHotkey: expressionController.triggerHotkey,
    };
}

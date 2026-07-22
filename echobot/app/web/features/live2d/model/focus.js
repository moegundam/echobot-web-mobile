export function normalizeFocusAxis(value, min, max, clamp) {
    const span = max - min;
    if (!Number.isFinite(span) || Math.abs(span) <= 0.0001) {
        return 0;
    }

    return clamp(((value - min) / span) * 2 - 1, -1, 1);
}

export function applyFocusTarget(focusController, rawX, rawY) {
    const distance = Math.hypot(rawX, rawY);
    if (!Number.isFinite(distance) || distance <= 0.0001) {
        focusController.focus(0, 0);
        return;
    }

    focusController.focus(rawX / distance, -rawY / distance);
}

export function createLive2DFocusController({ live2dState, clamp }) {
    function bind() {
        unbind();

        if (!live2dState.live2dStage) {
            return;
        }

        const pointerMove = (event) => {
            const globalPoint = event && event.data ? event.data.global : null;
            if (!globalPoint) {
                return;
            }

            live2dState.live2dLastPointerX = globalPoint.x;
            live2dState.live2dLastPointerY = globalPoint.y;
            updateFromGlobalPoint(globalPoint.x, globalPoint.y);
        };

        live2dState.live2dStage.on("pointermove", pointerMove);
        live2dState.live2dFocusHandlers = {
            pointerMove: pointerMove,
        };
        refreshFromLastPointer();
    }

    function unbind() {
        if (!live2dState.live2dFocusHandlers || !live2dState.live2dStage) {
            return;
        }

        live2dState.live2dStage.off("pointermove", live2dState.live2dFocusHandlers.pointerMove);
        live2dState.live2dFocusHandlers = null;
    }

    function refreshFromLastPointer() {
        if (
            !live2dState.live2dMouseFollowEnabled
            || !Number.isFinite(live2dState.live2dLastPointerX)
            || !Number.isFinite(live2dState.live2dLastPointerY)
        ) {
            return;
        }

        updateFromGlobalPoint(
            live2dState.live2dLastPointerX,
            live2dState.live2dLastPointerY,
        );
    }

    function updateFromGlobalPoint(globalX, globalY) {
        const model = live2dState.live2dModel;
        const internalModel = model && model.internalModel;
        if (
            !model
            || !internalModel
            || !internalModel.focusController
            || typeof internalModel.focusController.focus !== "function"
        ) {
            return;
        }

        const localPoint = toModelPoint(model, globalX, globalY);
        if (!localPoint) {
            return;
        }

        const rawFocusX = normalizeFocusAxis(
            localPoint.x,
            0,
            internalModel.originalWidth,
            clamp,
        );
        const visibleVerticalBounds = resolveVisibleVerticalBounds(model);
        const rawFocusY = visibleVerticalBounds
            ? normalizeFocusAxis(
                localPoint.y,
                visibleVerticalBounds.top,
                visibleVerticalBounds.bottom,
                clamp,
            )
            : normalizeFocusAxis(
                localPoint.y,
                0,
                internalModel.originalHeight,
                clamp,
            );

        applyFocusTarget(
            internalModel.focusController,
            rawFocusX,
            rawFocusY,
        );
    }

    function toModelPoint(model, globalX, globalY) {
        const pixi = globalThis.window && globalThis.window.PIXI;
        if (
            !pixi
            || typeof pixi.Point !== "function"
            || typeof model.toModelPosition !== "function"
        ) {
            return null;
        }

        const globalPoint = new pixi.Point(globalX, globalY);
        return model.toModelPosition(globalPoint, new pixi.Point());
    }

    function resolveVisibleVerticalBounds(model) {
        if (!live2dState.pixiApp || typeof model.getBounds !== "function") {
            return null;
        }

        const modelBounds = model.getBounds();
        const screen = live2dState.pixiApp.screen;
        if (
            !modelBounds
            || modelBounds.width <= 0
            || modelBounds.height <= 0
            || screen.width <= 0
            || screen.height <= 0
        ) {
            return null;
        }

        const visibleLeft = Math.max(modelBounds.x, screen.x);
        const visibleTop = Math.max(modelBounds.y, screen.y);
        const visibleRight = Math.min(
            modelBounds.x + modelBounds.width,
            screen.x + screen.width,
        );
        const visibleBottom = Math.min(
            modelBounds.y + modelBounds.height,
            screen.y + screen.height,
        );

        if (visibleRight <= visibleLeft || visibleBottom <= visibleTop) {
            return null;
        }

        const topPoint = toModelPoint(model, visibleLeft, visibleTop);
        const bottomPoint = toModelPoint(model, visibleLeft, visibleBottom);
        if (!topPoint || !bottomPoint) {
            return null;
        }

        const top = Math.min(topPoint.y, bottomPoint.y);
        const bottom = Math.max(topPoint.y, bottomPoint.y);
        if (bottom - top <= 0.0001) {
            return null;
        }

        return {
            top: top,
            bottom: bottom,
        };
    }

    function applyMouseFollowSetting() {
        const model = live2dState.live2dModel;
        if (!model) {
            return;
        }

        model.interactive = true;
        model.autoInteract = false;
        if (typeof model.unregisterInteraction === "function") {
            model.unregisterInteraction();
        }

        if (!live2dState.live2dMouseFollowEnabled) {
            unbind();
            reset();
            return;
        }

        bind();
    }

    function reset() {
        const internalModel = live2dState.live2dModel && live2dState.live2dModel.internalModel;
        if (
            !internalModel
            || !internalModel.focusController
            || typeof internalModel.focusController.focus !== "function"
        ) {
            return;
        }

        internalModel.focusController.focus(0, 0, true);
    }

    return {
        applyMouseFollowSetting,
        bind,
        refreshFromLastPointer,
        reset,
        unbind,
    };
}

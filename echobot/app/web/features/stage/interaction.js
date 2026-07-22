const STAGE_LIVE2D_ZOOM_STEP = 1.08;


export function createStageInteractionController({
    stageSurface,
    canvasHost,
    zoomOutButton,
    zoomResetButton,
    zoomInButton,
    live2d,
    isMenuOpen,
}) {
    let stageDragState = null;
    let stagePinchStartDistance = 0;
    let stagePinchStartZoom = 1;
    let stagePinchActive = false;
    let stageGestureStartZoom = 1;

    function bind() {
        if (!stageSurface) {
            return;
        }

        stageSurface.addEventListener("wheel", handleStageWheelZoom, { passive: false });
        stageSurface.addEventListener("touchstart", handleStageTouchStart, { passive: true });
        stageSurface.addEventListener("touchmove", handleStageTouchMove, { passive: false });
        stageSurface.addEventListener("touchend", handleStageTouchEnd, { passive: true });
        stageSurface.addEventListener("touchcancel", handleStageTouchEnd, { passive: true });
        stageSurface.addEventListener("gesturestart", handleStageGestureStart, { passive: false });
        stageSurface.addEventListener("gesturechange", handleStageGestureChange, { passive: false });
        stageSurface.addEventListener("gestureend", handleStageGestureEnd, { passive: true });

        canvasHost?.addEventListener("pointerdown", handleStagePointerDown);
        canvasHost?.addEventListener("pointermove", handleStagePointerMove);
        canvasHost?.addEventListener("pointerup", handleStagePointerUp);
        canvasHost?.addEventListener("pointercancel", handleStagePointerUp);
        canvasHost?.addEventListener("lostpointercapture", handleStagePointerUp);
        zoomOutButton?.addEventListener("click", () => {
            live2d.adjustZoom(1 / STAGE_LIVE2D_ZOOM_STEP);
        });
        zoomResetButton?.addEventListener("click", () => {
            live2d.resetZoom();
        });
        zoomInButton?.addEventListener("click", () => {
            live2d.adjustZoom(STAGE_LIVE2D_ZOOM_STEP);
        });
    }

    function handleStagePointerDown(event) {
        if (!live2d.canAdjustView() || shouldIgnoreStageViewEvent(event)) {
            return;
        }
        if (event.pointerType === "mouse" && event.button !== 0) {
            return;
        }
        if (stagePinchActive) {
            return;
        }

        event.preventDefault();
        const view = live2d.getView();
        stageDragState = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            offsetX: view.offsetX,
            offsetY: view.offsetY,
        };
        canvasHost?.classList.add("is-stage-dragging");
        try {
            canvasHost?.setPointerCapture?.(event.pointerId);
        } catch (_error) {
            // Pointer capture is optional across browsers.
        }
    }

    function handleStagePointerMove(event) {
        if (
            !stageDragState
            || stagePinchActive
            || event.pointerId !== stageDragState.pointerId
            || !live2d.canAdjustView()
        ) {
            return;
        }

        event.preventDefault();
        live2d.setOffsets(
            stageDragState.offsetX + (event.clientX - stageDragState.startX),
            stageDragState.offsetY + (event.clientY - stageDragState.startY),
            { persist: false },
        );
    }

    function handleStagePointerUp(event) {
        if (!stageDragState || event.pointerId !== stageDragState.pointerId) {
            return;
        }

        cancelStageDrag();
    }

    function cancelStageDrag(options = {}) {
        if (!stageDragState) {
            return;
        }
        const pointerId = stageDragState.pointerId;
        try {
            canvasHost?.releasePointerCapture?.(pointerId);
        } catch (_error) {
            // Pointer capture may already be released.
        }
        stageDragState = null;
        canvasHost?.classList.remove("is-stage-dragging");
        if (options.persist !== false) {
            live2d.persistView();
        }
    }

    function handleStageWheelZoom(event) {
        if (!live2d.canAdjustView() || shouldIgnoreStageViewEvent(event)) {
            return;
        }

        const deltaY = Number(event.deltaY);
        if (!Number.isFinite(deltaY) || deltaY === 0) {
            return;
        }

        event.preventDefault();
        const direction = deltaY < 0 ? 1 : -1;
        const wheelMagnitude = Math.min(Math.abs(deltaY), 600) / 120;
        const step = Math.pow(STAGE_LIVE2D_ZOOM_STEP, Math.max(wheelMagnitude, 0.35));
        live2d.adjustZoom(direction > 0 ? step : 1 / step);
    }

    function handleStageTouchStart(event) {
        if (
            !live2d.canAdjustZoom()
            || !event.touches
            || event.touches.length !== 2
            || shouldIgnoreStageZoomEvent(event)
        ) {
            stagePinchActive = false;
            return;
        }

        cancelStageDrag();
        stagePinchStartDistance = distanceBetweenTouches(event.touches[0], event.touches[1]);
        stagePinchStartZoom = live2d.getZoom();
        stagePinchActive = stagePinchStartDistance > 0;
    }

    function handleStageTouchMove(event) {
        if (
            !stagePinchActive
            || !live2d.canAdjustZoom()
            || !event.touches
            || event.touches.length !== 2
        ) {
            return;
        }

        const nextDistance = distanceBetweenTouches(event.touches[0], event.touches[1]);
        if (nextDistance <= 0 || stagePinchStartDistance <= 0) {
            return;
        }

        event.preventDefault();
        live2d.setZoom(stagePinchStartZoom * (nextDistance / stagePinchStartDistance));
    }

    function handleStageTouchEnd(event) {
        if (!event.touches || event.touches.length < 2) {
            const wasPinching = stagePinchActive;
            stagePinchActive = false;
            stagePinchStartDistance = 0;
            stagePinchStartZoom = live2d.getZoom();
            if (wasPinching) {
                live2d.persistView();
            }
        }
    }

    function handleStageGestureStart(event) {
        if (!live2d.canAdjustZoom() || shouldIgnoreStageZoomEvent(event)) {
            return;
        }
        event.preventDefault();
        stageGestureStartZoom = live2d.getZoom();
    }

    function handleStageGestureChange(event) {
        if (!live2d.canAdjustZoom() || shouldIgnoreStageZoomEvent(event)) {
            return;
        }
        const gestureScale = Number(event.scale);
        if (!Number.isFinite(gestureScale) || gestureScale <= 0) {
            return;
        }
        event.preventDefault();
        live2d.setZoom(stageGestureStartZoom * gestureScale);
    }

    function handleStageGestureEnd() {
        stageGestureStartZoom = live2d.getZoom();
    }

    function handleStageZoomKeyDown(event) {
        if (!live2d.canAdjustZoom() || shouldIgnoreStageZoomKeyEvent(event)) {
            return;
        }

        if (event.key === "+" || event.key === "=" || event.code === "NumpadAdd") {
            event.preventDefault();
            live2d.adjustZoom(STAGE_LIVE2D_ZOOM_STEP);
            return;
        }
        if (event.key === "-" || event.code === "NumpadSubtract") {
            event.preventDefault();
            live2d.adjustZoom(1 / STAGE_LIVE2D_ZOOM_STEP);
            return;
        }
        if (event.key === "0" || event.code === "Numpad0") {
            event.preventDefault();
            live2d.resetZoom();
        }
    }

    function shouldIgnoreStageZoomEvent(event) {
        return shouldIgnoreStageViewEvent(event);
    }

    function shouldIgnoreStageViewEvent(event) {
        const target = event && event.target;
        if (!target || typeof target.closest !== "function") {
            return false;
        }
        return Boolean(target.closest(
            "button, a, input, select, textarea, [role='button'], #stage-menu-panel, #stage-menu-backdrop",
        ));
    }

    function shouldIgnoreStageZoomKeyEvent(event) {
        const target = event && event.target;
        if (!target || typeof target.closest !== "function") {
            return false;
        }
        if (target.closest("input, select, textarea, [contenteditable='true']")) {
            return true;
        }
        return Boolean(isMenuOpen?.() && target.closest("#stage-menu-panel"));
    }

    return {
        bind,
        handleStagePointerDown,
        handleStagePointerMove,
        handleStageTouchStart,
        handleStageTouchMove,
        handleStageZoomKeyDown,
    };
}


function distanceBetweenTouches(firstTouch, secondTouch) {
    const deltaX = Number(firstTouch.clientX) - Number(secondTouch.clientX);
    const deltaY = Number(firstTouch.clientY) - Number(secondTouch.clientY);
    return Math.sqrt((deltaX * deltaX) + (deltaY * deltaY));
}

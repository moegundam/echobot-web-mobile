export const LIVE2D_MIN_SCALE = 0.08;
export const LIVE2D_MAX_SCALE = 3.2;

export function normalizeSelectionKey(value) {
    return String(value || "").trim();
}

export function selectionKeyFromConfig(live2dConfig) {
    return normalizeSelectionKey(
        live2dConfig && (live2dConfig.selection_key || live2dConfig.model_url),
    );
}

export function calculateDefaultTransform({ stageWidth, stageHeight, baseSize }) {
    const width = Number(stageWidth);
    const height = Number(stageHeight);
    const widthRatio = width / Math.max(Number(baseSize.width), 1);
    const heightRatio = height / Math.max(Number(baseSize.height), 1);
    return {
        x: width * 0.5,
        y: height * 0.62,
        scale: Math.min(widthRatio, heightRatio) * 0.82,
    };
}

export function calculateResizedTransform({
    modelX,
    modelY,
    modelScale,
    previousStageSize,
    currentStageSize,
    clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum),
    normalizedX = null,
    normalizedY = null,
}) {
    const previousWidth = Number(previousStageSize && previousStageSize.width);
    const previousHeight = Number(previousStageSize && previousStageSize.height);
    const currentWidth = Math.max(Number(currentStageSize && currentStageSize.width) || 0, 1);
    const currentHeight = Math.max(Number(currentStageSize && currentStageSize.height) || 0, 1);
    if (
        !Number.isFinite(previousWidth)
        || !Number.isFinite(previousHeight)
        || previousWidth <= 0
        || previousHeight <= 0
        || (previousWidth === currentWidth && previousHeight === currentHeight)
    ) {
        return null;
    }

    const scaleRatio = Math.min(
        currentWidth / previousWidth,
        currentHeight / previousHeight,
    );
    const positionX = Number.isFinite(normalizedX)
        ? normalizedX
        : Number(modelX) / previousWidth;
    const positionY = Number.isFinite(normalizedY)
        ? normalizedY
        : Number(modelY) / previousHeight;
    return {
        x: clamp(positionX * currentWidth, currentWidth * 0.08, currentWidth * 0.92),
        y: clamp(positionY * currentHeight, currentHeight * 0.12, currentHeight * 0.92),
        scale: clamp(Number(modelScale) * scaleRatio, LIVE2D_MIN_SCALE, LIVE2D_MAX_SCALE),
    };
}

export function measureLive2DBaseSize(model) {
    if (typeof model.getLocalBounds === "function") {
        const bounds = model.getLocalBounds();
        if (bounds && bounds.width > 0 && bounds.height > 0) {
            return {
                width: bounds.width,
                height: bounds.height,
            };
        }
    }

    const scaleX = Math.max(Math.abs(model.scale.x) || 0, 0.0001);
    const scaleY = Math.max(Math.abs(model.scale.y) || 0, 0.0001);
    return {
        width: model.width / scaleX,
        height: model.height / scaleY,
    };
}

export function canRestoreSavedTransform(payload, currentStageSize) {
    const savedWidth = Number(payload && payload.stageWidth);
    const savedHeight = Number(payload && payload.stageHeight);
    const currentWidth = Math.max(Number(currentStageSize && currentStageSize.width), 1);
    const currentHeight = Math.max(Number(currentStageSize && currentStageSize.height), 1);
    if (
        !Number.isFinite(savedWidth)
        || !Number.isFinite(savedHeight)
        || savedWidth <= 0
        || savedHeight <= 0
    ) {
        return false;
    }

    const widthRatio = savedWidth / currentWidth;
    const heightRatio = savedHeight / currentHeight;
    return (
        widthRatio >= 0.72
        && widthRatio <= 1.38
        && heightRatio >= 0.72
        && heightRatio <= 1.38
    );
}

export function buildTransformSnapshot({ storageKey, model, stageSize, roundTo }) {
    return {
        storageKey: storageKey,
        transform: {
            x: roundTo(model.x, 2),
            y: roundTo(model.y, 2),
            scale: roundTo(model.scale.x, 4),
            stageWidth: roundTo(stageSize.width, 2),
            stageHeight: roundTo(stageSize.height, 2),
        },
    };
}

export function shouldIgnoreStageWheel(event) {
    const target = event && event.target;
    if (!target || typeof target.closest !== "function") {
        return false;
    }

    return Boolean(target.closest("#live2d-drawer, #live2d-drawer-backdrop"));
}

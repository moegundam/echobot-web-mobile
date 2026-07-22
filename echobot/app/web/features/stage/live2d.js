import {
    readJson,
    removeStoredValue,
    writeJson,
} from "../../core/storage.js?v=stage-view-1";
import { responseToError } from "../../modules/api.js";
import { fetchStageWebConfig } from "./api.js";


const DEFAULT_LIP_SYNC_IDS = ["ParamMouthOpenY", "PARAM_MOUTH_OPEN_Y", "MouthOpenY"];
const STAGE_LIVE2D_VIEW_STORAGE_PREFIX = "echobot.stage.live2d.view";
const STAGE_LIVE2D_ZOOM_MIN = 0.45;
const STAGE_LIVE2D_ZOOM_MAX = 2.6;
const STAGE_LIVE2D_PAN_LIMIT_FACTOR = 0.85;


export function createStageLive2DController({
    canvasHost,
    zoomOutButton,
    zoomResetButton,
    zoomInButton,
    i18n,
    getContext,
    getSessionName,
    onStatus,
}) {
    let live2dApp = null;
    let live2dModel = null;
    let live2dConfig = null;
    let live2dLoadPromise = null;
    let stageLive2DBaseScale = 1;
    let stageLive2DZoom = 1;
    let stageLive2DOffsetX = 0;
    let stageLive2DOffsetY = 0;
    let activeStageExpressionDefinition = null;
    let stageExpressionHook = null;
    let live2dReloadToken = 0;
    const expressionDataCache = new Map();

    function getConfig() {
        return live2dConfig;
    }

    function getKey() {
        const contextLive2D = getContextLive2DConfig();
        return contextLive2D
            ? String(contextLive2D.selection_key || contextLive2D.model_url || "")
            : "";
    }

    async function init() {
        if (!canvasHost) {
            return;
        }

        const contextConfig = getContextLive2DConfig();
        let config = null;
        try {
            config = await fetchStageWebConfig();
        } catch (error) {
            console.warn("Unable to load web config", error);
            if (!contextConfig) {
                markLive2DUnavailable("stage.fallback.configUnavailable");
                return;
            }
        }

        live2dConfig = normalizeLive2DConfig(
            resolveStageLive2DConfig(contextConfig, config && config.live2d),
            contextConfig ? "session" : "web-config",
        );
        const savedView = loadSavedStageLive2DView();
        stageLive2DZoom = savedView.zoom;
        stageLive2DOffsetX = savedView.offsetX;
        stageLive2DOffsetY = savedView.offsetY;
        updateStageZoomControls();
        const modelUrl = live2dConfig.model_url;
        canvasHost.dataset.live2dSource = live2dConfig.source;
        canvasHost.dataset.live2dSelectionKey = live2dConfig.selection_key;
        canvasHost.dataset.live2dModelUrl = modelUrl;
        if (!modelUrl) {
            markLive2DUnavailable("stage.fallback.subtitleMode");
            return;
        }

        const live2dReadiness = canUsePixiLive2D();
        if (!live2dReadiness.ready) {
            markLive2DUnavailable(live2dReadiness.messageKey);
            return;
        }

        try {
            await withPixiInitializationGuard(async () => {
                live2dApp = await createPixiApplication(canvasHost);
                live2dModel = await window.PIXI.live2d.Live2DModel.from(modelUrl, {
                    autoInteract: false,
                });
                if (live2dModel.anchor && typeof live2dModel.anchor.set === "function") {
                    live2dModel.anchor.set(0.5, 0.5);
                }
                live2dModel.interactive = true;
                live2dModel.cursor = "grab";
                live2dApp.stage.addChild(live2dModel);
                attachStageExpressionHook(live2dModel);
                fitLive2DModel();
                window.addEventListener("resize", fitLive2DModel);
                updateStageZoomControls();
                canvasHost.dataset.live2d = "ready";
                canvasHost.dataset.live2dSource = live2dConfig.source;
                canvasHost.dataset.live2dSelectionKey = live2dConfig.selection_key;
                canvasHost.dataset.live2dModelUrl = modelUrl;
            });
        } catch (error) {
            console.warn("Live2D initialization failed", error);
            markLive2DUnavailable(
                isKnownPixiInitializationNoise([error])
                    ? "stage.fallback.webglUnavailable"
                    : "stage.fallback.subtitleMode",
            );
        }
    }

    async function reloadFromContext() {
        const requestToken = ++live2dReloadToken;
        if (live2dLoadPromise) {
            try {
                await live2dLoadPromise;
            } catch (_error) {
                // The latest request still gets one clean retry below.
            }
            if (requestToken !== live2dReloadToken) {
                return;
            }
        }
        const loadPromise = (async () => {
            destroyLive2DApp();
            if (canvasHost) {
                canvasHost.textContent = "";
                delete canvasHost.dataset.i18nFallbackKey;
            }
            await init();
        })();
        live2dLoadPromise = loadPromise;
        try {
            await loadPromise;
        } finally {
            if (live2dLoadPromise === loadPromise) {
                live2dLoadPromise = null;
            }
        }
    }

    function applyVisualState(payload) {
        if (!payload) {
            return;
        }
        if (payload.expression || payload.emotion) {
            void applyStageExpression(payload.expression || payload.emotion);
        }
        if (payload.motion) {
            void playStageMotion(payload.motion);
        }
    }

    function applyMouthValue(value) {
        const internalModel = live2dModel && live2dModel.internalModel;
        const coreModel = internalModel && internalModel.coreModel;
        if (!coreModel || typeof coreModel.setParameterValueById !== "function") {
            return;
        }

        const lipSyncIds = Array.isArray(live2dConfig && live2dConfig.lip_sync_parameter_ids)
            && live2dConfig.lip_sync_parameter_ids.length > 0
            ? live2dConfig.lip_sync_parameter_ids
            : DEFAULT_LIP_SYNC_IDS;

        lipSyncIds.forEach((parameterId) => {
            try {
                coreModel.setParameterValueById(parameterId, value);
            } catch (error) {
                console.warn(`Failed to update Live2D mouth parameter ${parameterId}`, error);
            }
        });

        if (live2dConfig && live2dConfig.mouth_form_parameter_id) {
            try {
                coreModel.setParameterValueById(live2dConfig.mouth_form_parameter_id, 0);
            } catch (error) {
                console.warn("Failed to reset Live2D mouth form parameter", error);
            }
        }
    }

    function canAdjustZoom() {
        return canAdjustView();
    }

    function canAdjustView() {
        return Boolean(
            live2dModel
            && live2dModel.scale
            && typeof live2dModel.scale.set === "function"
            && live2dApp
            && canvasHost,
        );
    }

    function getZoom() {
        return stageLive2DZoom;
    }

    function getView() {
        return {
            offsetX: stageLive2DOffsetX,
            offsetY: stageLive2DOffsetY,
            zoom: stageLive2DZoom,
        };
    }

    function adjustZoom(scaleFactor, options = {}) {
        const factor = Number(scaleFactor);
        if (!Number.isFinite(factor) || factor <= 0) {
            return;
        }
        setZoom(stageLive2DZoom * factor, options);
    }

    function setZoom(nextZoom, options = {}) {
        stageLive2DZoom = clampNumber(
            nextZoom,
            STAGE_LIVE2D_ZOOM_MIN,
            STAGE_LIVE2D_ZOOM_MAX,
            1,
        );
        applyStageLive2DView(options);
    }

    function resetZoom() {
        stageLive2DZoom = 1;
        stageLive2DOffsetX = 0;
        stageLive2DOffsetY = 0;
        removeStoredValue(stageLive2DViewStorageKey());
        removeStoredValue(stageLegacyLive2DZoomStorageKey());
        applyStageLive2DView({ persist: false });
    }

    function setOffsets(offsetX, offsetY, options = {}) {
        stageLive2DOffsetX = offsetX;
        stageLive2DOffsetY = offsetY;
        clampStageLive2DOffset();
        applyStageLive2DView(options);
    }

    function persistView() {
        writeJson(stageLive2DViewStorageKey(), {
            zoom: stageLive2DZoom,
            offsetX: Math.round(stageLive2DOffsetX * 100) / 100,
            offsetY: Math.round(stageLive2DOffsetY * 100) / 100,
            stageWidth: Math.round(Math.max(canvasHost?.clientWidth || 0, 1) * 100) / 100,
            stageHeight: Math.round(Math.max(canvasHost?.clientHeight || 0, 1) * 100) / 100,
        });
    }

    function refreshLocalizedText() {
        if (canvasHost && canvasHost.dataset.i18nFallbackKey) {
            canvasHost.textContent = i18n.t(canvasHost.dataset.i18nFallbackKey);
        }
    }

    function destroy() {
        destroyLive2DApp();
    }

    function getContextLive2DConfig() {
        const context = getContext();
        const contextLive2D = context && typeof context.live2d_model === "object"
            ? context.live2d_model
            : null;
        if (
            !contextLive2D
            || contextLive2D.available === false
            || !contextLive2D.model_url
        ) {
            return null;
        }
        return contextLive2D;
    }

    function normalizeLive2DConfig(sourceConfig, source = "web-config") {
        if (!sourceConfig || sourceConfig.available === false) {
            return emptyLive2DConfig(source);
        }

        const selectedModel = Array.isArray(sourceConfig.models)
            ? sourceConfig.models.find((model) => model && model.model_url)
            : null;
        const modelConfig = selectedModel || sourceConfig;
        if (!modelConfig || modelConfig.available === false) {
            return emptyLive2DConfig(source);
        }
        const lipSyncParameterIds = Array.isArray(modelConfig.lip_sync_parameter_ids)
            ? modelConfig.lip_sync_parameter_ids.filter((item) => typeof item === "string")
            : [];
        return {
            selection_key: String(modelConfig.selection_key || sourceConfig.selection_key || ""),
            source,
            model_url: String(modelConfig.model_url || ""),
            lip_sync_parameter_ids: lipSyncParameterIds.length > 0
                ? lipSyncParameterIds
                : DEFAULT_LIP_SYNC_IDS.slice(),
            mouth_form_parameter_id: typeof modelConfig.mouth_form_parameter_id === "string"
                ? modelConfig.mouth_form_parameter_id
                : null,
            expressions: normalizeLive2DActionList(modelConfig.expressions),
            motions: normalizeLive2DActionList(modelConfig.motions),
        };
    }

    function emptyLive2DConfig(source) {
        return {
            selection_key: "",
            source,
            model_url: "",
            lip_sync_parameter_ids: DEFAULT_LIP_SYNC_IDS.slice(),
            mouth_form_parameter_id: null,
            expressions: [],
            motions: [],
        };
    }

    function resolveStageLive2DConfig(contextConfig, webLive2DConfig) {
        if (!contextConfig) {
            return webLive2DConfig;
        }
        return {
            ...live2DWebCatalogMatch(webLive2DConfig, contextConfig),
            ...contextConfig,
            available: contextConfig.available !== false,
        };
    }

    function live2DWebCatalogMatch(webLive2DConfig, contextConfig) {
        const models = webLive2DConfig && Array.isArray(webLive2DConfig.models)
            ? webLive2DConfig.models
            : [];
        const selectionKey = String(contextConfig.selection_key || "");
        const modelUrl = String(contextConfig.model_url || "");
        return models.find((model) => {
            if (!model || typeof model !== "object") {
                return false;
            }
            return (
                (selectionKey && model.selection_key === selectionKey)
                || (modelUrl && model.model_url === modelUrl)
            );
        }) || {};
    }

    function normalizeLive2DActionList(items) {
        return Array.isArray(items)
            ? items
                .filter((item) => item && typeof item === "object")
                .map((item) => ({
                    file: String(item.file || ""),
                    name: String(item.name || item.file || ""),
                    note: String(item.note || ""),
                    url: String(item.url || ""),
                    group: String(item.group || ""),
                    index: Number.isInteger(item.index) ? item.index : 0,
                }))
                .filter((item) => item.file || item.name)
            : [];
    }

    async function applyStageExpression(expressionName) {
        const expressionItem = findLive2DExpression(expressionName);
        if (!expressionItem || !live2dModel) {
            return;
        }

        try {
            const expressionDefinition = await loadStageExpressionDefinition(expressionItem);
            activeStageExpressionDefinition = expressionDefinition;
            applyActiveStageExpression();
        } catch (error) {
            console.warn("Failed to apply stage expression", error);
        }
    }

    function applyActiveStageExpression() {
        if (!activeStageExpressionDefinition) {
            return;
        }
        applyStageExpressionDefinition(activeStageExpressionDefinition);
    }

    function applyStageExpressionDefinition(expressionDefinition) {
        const internalModel = live2dModel && live2dModel.internalModel;
        const coreModel = internalModel && internalModel.coreModel;
        if (!coreModel || typeof coreModel.setParameterValueById !== "function") {
            return;
        }

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
                console.warn(`Failed to apply stage expression parameter ${parameter.id}`, error);
            }
        });
    }

    async function playStageMotion(motionName) {
        const motionItem = findLive2DMotion(motionName);
        if (!motionItem || !live2dModel || typeof live2dModel.motion !== "function") {
            return;
        }

        try {
            await live2dModel.motion(motionItem.group, motionItem.index);
        } catch (error) {
            console.warn("Failed to play stage motion", error);
        }
    }

    function findLive2DExpression(expressionName) {
        const normalizedName = normalizeStageDirective(expressionName);
        const expressions = live2dConfig && Array.isArray(live2dConfig.expressions)
            ? live2dConfig.expressions
            : [];
        if (!normalizedName || expressions.length === 0) {
            return null;
        }
        return expressions.find((item) => (
            item.url
            && directiveMatchesLive2DItem(item, normalizedName)
        )) || null;
    }

    function findLive2DMotion(motionName) {
        const normalizedName = normalizeStageDirective(motionName);
        const motions = live2dConfig && Array.isArray(live2dConfig.motions)
            ? live2dConfig.motions
            : [];
        if (!normalizedName || motions.length === 0) {
            return null;
        }
        return motions.find((item) => directiveMatchesLive2DItem(item, normalizedName)) || null;
    }

    function directiveMatchesLive2DItem(item, normalizedName) {
        if (!item || !normalizedName) {
            return false;
        }
        return [item.file, item.name, item.note]
            .some((value) => normalizeStageDirective(value) === normalizedName);
    }

    function normalizeStageDirective(value) {
        return String(value || "").trim().toLowerCase();
    }

    async function loadStageExpressionDefinition(expressionItem) {
        if (expressionDataCache.has(expressionItem.url)) {
            return expressionDataCache.get(expressionItem.url);
        }

        const response = await fetch(expressionItem.url, { cache: "no-store" });
        if (!response.ok) {
            throw await responseToError(response);
        }

        const payload = await response.json();
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
        const expressionDefinition = { parameters };
        expressionDataCache.set(expressionItem.url, expressionDefinition);
        return expressionDefinition;
    }

    function normalizeExpressionBlend(blend) {
        const normalizedBlend = String(blend || "").trim().toLowerCase();
        if (normalizedBlend === "add") {
            return "Add";
        }
        if (normalizedBlend === "multiply") {
            return "Multiply";
        }
        return "Set";
    }

    function attachStageExpressionHook(model) {
        detachStageExpressionHook();
        const internalModel = model && model.internalModel;
        if (!internalModel || typeof internalModel.on !== "function") {
            return;
        }
        stageExpressionHook = () => {
            applyActiveStageExpression();
        };
        internalModel.on("beforeModelUpdate", stageExpressionHook);
    }

    function detachStageExpressionHook() {
        if (!stageExpressionHook || !live2dModel || !live2dModel.internalModel) {
            stageExpressionHook = null;
            return;
        }
        const internalModel = live2dModel.internalModel;
        if (typeof internalModel.off === "function") {
            internalModel.off("beforeModelUpdate", stageExpressionHook);
        }
        stageExpressionHook = null;
    }

    function canUsePixiLive2D() {
        if (!window.PIXI || !window.PIXI.live2d || !window.PIXI.live2d.Live2DModel) {
            return {
                ready: false,
                messageKey: "stage.fallback.live2dUnavailable",
            };
        }
        if (!canCreateWebGLShaderProgram()) {
            return {
                ready: false,
                messageKey: "stage.fallback.webglUnavailable",
            };
        }
        return { ready: true, messageKey: "" };
    }

    function canCreateWebGLShaderProgram() {
        const documentRef = window.document;
        if (!documentRef || typeof documentRef.createElement !== "function") {
            return false;
        }

        const canvas = documentRef.createElement("canvas");
        let gl = null;
        try {
            gl = canvas.getContext("webgl2")
                || canvas.getContext("webgl")
                || canvas.getContext("experimental-webgl");
        } catch (_error) {
            return false;
        }
        if (!gl || typeof gl.createShader !== "function") {
            return false;
        }

        const vertexShader = compileWebGLShader(
            gl,
            gl.VERTEX_SHADER,
            "attribute vec2 position; void main(){ gl_Position = vec4(position, 0.0, 1.0); }",
        );
        const fragmentShader = compileWebGLShader(
            gl,
            gl.FRAGMENT_SHADER,
            "void main(){ gl_FragColor = vec4(1.0); }",
        );
        if (!vertexShader || !fragmentShader) {
            deleteWebGLShader(gl, vertexShader);
            deleteWebGLShader(gl, fragmentShader);
            return false;
        }

        const program = gl.createProgram();
        if (!program) {
            deleteWebGLShader(gl, vertexShader);
            deleteWebGLShader(gl, fragmentShader);
            return false;
        }

        gl.attachShader(program, vertexShader);
        gl.attachShader(program, fragmentShader);
        gl.linkProgram(program);
        const linkSucceeded = Boolean(gl.getProgramParameter(program, gl.LINK_STATUS));
        deleteWebGLProgram(gl, program);
        deleteWebGLShader(gl, vertexShader);
        deleteWebGLShader(gl, fragmentShader);
        return linkSucceeded;
    }

    function compileWebGLShader(gl, type, source) {
        const shader = gl.createShader(type);
        if (!shader) {
            return null;
        }
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            gl.deleteShader(shader);
            return null;
        }
        return shader;
    }

    function deleteWebGLProgram(gl, program) {
        if (!gl || !program || typeof gl.deleteProgram !== "function") {
            return;
        }
        gl.deleteProgram(program);
    }

    function deleteWebGLShader(gl, shader) {
        if (!gl || !shader || typeof gl.deleteShader !== "function") {
            return;
        }
        gl.deleteShader(shader);
    }

    async function withPixiInitializationGuard(callback) {
        const originalConsoleError = console.error;
        console.error = (...args) => {
            if (isKnownPixiInitializationNoise(args)) {
                return;
            }
            originalConsoleError.apply(console, args);
        };
        try {
            return await callback();
        } finally {
            console.error = originalConsoleError;
        }
    }

    function isKnownPixiInitializationNoise(args) {
        return args.some((item) => {
            const text = String(item && item.message ? item.message : item);
            return (
                text.includes("PixiJS Error: Could not initialize shader")
                || text.includes("Could not initialize shader")
            );
        });
    }

    async function createPixiApplication(host) {
        let app;
        if (typeof window.PIXI.Application === "function") {
            app = new window.PIXI.Application({
                resizeTo: host,
                autoStart: true,
                backgroundAlpha: 0,
                antialias: true,
            });
        } else {
            throw new Error("PIXI.Application is unavailable");
        }

        if (typeof app.init === "function") {
            await app.init({
                resizeTo: host,
                autoStart: true,
                backgroundAlpha: 0,
                antialias: true,
            });
        }

        const canvas = app.canvas || app.view;
        if (canvas) {
            host.replaceChildren(canvas);
        }
        return app;
    }

    function destroyLive2DApp() {
        window.removeEventListener("resize", fitLive2DModel);
        applyMouthValue(0);
        detachStageExpressionHook();
        activeStageExpressionDefinition = null;
        live2dModel = null;
        stageLive2DBaseScale = 1;
        canvasHost?.classList.remove("is-stage-dragging");
        if (live2dApp && typeof live2dApp.destroy === "function") {
            try {
                live2dApp.destroy(true, {
                    children: true,
                    texture: true,
                    baseTexture: true,
                });
            } catch (_error) {
                // Fallback rendering should keep working even if PIXI cleanup fails.
            }
        }
        live2dApp = null;
        updateStageZoomControls();
    }

    function fitLive2DModel() {
        if (!live2dModel || !live2dApp || !canvasHost) {
            return;
        }

        const width = Math.max(canvasHost.clientWidth, 1);
        const height = Math.max(canvasHost.clientHeight, 1);
        if (live2dApp.renderer && typeof live2dApp.renderer.resize === "function") {
            live2dApp.renderer.resize(width, height);
        }

        if (live2dModel.anchor && typeof live2dModel.anchor.set === "function") {
            live2dModel.anchor.set(0.5, 0.5);
        }

        const modelBounds = measureStageLive2DBaseSize();
        const modelWidth = Math.max(modelBounds.width || width, 1);
        const modelHeight = Math.max(modelBounds.height || height, 1);
        const scale = Math.min(width / modelWidth, height / modelHeight) * 0.82;
        stageLive2DBaseScale = Math.max(scale, 0.05);
        clampStageLive2DOffset();
        applyStageLive2DView({ persist: false });
    }

    function applyStageLive2DView(options = {}) {
        if (!canAdjustView()) {
            updateStageZoomControls();
            return;
        }

        live2dModel.scale.set(stageLive2DBaseScale * stageLive2DZoom);
        live2dModel.x = (canvasHost.clientWidth * 0.5) + stageLive2DOffsetX;
        live2dModel.y = (canvasHost.clientHeight * 0.62) + stageLive2DOffsetY;
        if (options.persist !== false) {
            persistView();
        }
        updateStageZoomControls();
    }

    function loadSavedStageLive2DView() {
        const payload = readJson(stageLive2DViewStorageKey())
            || readJson(stageLegacyLive2DZoomStorageKey());
        if (!payload) {
            return { zoom: 1, offsetX: 0, offsetY: 0 };
        }
        const savedZoom = typeof payload === "number"
            ? payload
            : Number(payload && payload.zoom);
        return {
            zoom: clampNumber(savedZoom, STAGE_LIVE2D_ZOOM_MIN, STAGE_LIVE2D_ZOOM_MAX, 1),
            offsetX: clampStageOffsetNumber(payload && payload.offsetX, "x"),
            offsetY: clampStageOffsetNumber(payload && payload.offsetY, "y"),
        };
    }

    function stageLive2DViewStorageKey() {
        const live2DKey = live2dConfig
            ? String(live2dConfig.selection_key || live2dConfig.model_url || "default")
            : "default";
        return [
            STAGE_LIVE2D_VIEW_STORAGE_PREFIX,
            encodeURIComponent(getSessionName() || "default"),
            encodeURIComponent(live2DKey || "default"),
        ].join(".");
    }

    function stageLegacyLive2DZoomStorageKey() {
        const live2DKey = live2dConfig
            ? String(live2dConfig.selection_key || live2dConfig.model_url || "default")
            : "default";
        return [
            "echobot.stage.live2d.zoom",
            encodeURIComponent(getSessionName() || "default"),
            encodeURIComponent(live2DKey || "default"),
        ].join(".");
    }

    function measureStageLive2DBaseSize() {
        if (!live2dModel) {
            return {
                width: canvasHost?.clientWidth || 1,
                height: canvasHost?.clientHeight || 1,
            };
        }
        if (typeof live2dModel.getLocalBounds === "function") {
            const bounds = live2dModel.getLocalBounds();
            if (bounds && bounds.width > 0 && bounds.height > 0) {
                return { width: bounds.width, height: bounds.height };
            }
        }
        const scaleX = Math.max(Math.abs(live2dModel.scale?.x) || 0, 0.0001);
        const scaleY = Math.max(Math.abs(live2dModel.scale?.y) || 0, 0.0001);
        return {
            width: (live2dModel.width || 1) / scaleX,
            height: (live2dModel.height || 1) / scaleY,
        };
    }

    function clampStageLive2DOffset() {
        stageLive2DOffsetX = clampStageOffsetNumber(stageLive2DOffsetX, "x");
        stageLive2DOffsetY = clampStageOffsetNumber(stageLive2DOffsetY, "y");
    }

    function clampStageOffsetNumber(value, axis) {
        const number = Number.parseFloat(String(value));
        if (!Number.isFinite(number)) {
            return 0;
        }
        const rawSize = axis === "y"
            ? Number(canvasHost?.clientHeight || 0)
            : Number(canvasHost?.clientWidth || 0);
        const size = Number.isFinite(rawSize) && rawSize > 1 ? rawSize : 1000;
        return clamp(number, -size * STAGE_LIVE2D_PAN_LIMIT_FACTOR, size * STAGE_LIVE2D_PAN_LIMIT_FACTOR);
    }

    function updateStageZoomControls() {
        const ready = canAdjustView();
        [zoomOutButton, zoomResetButton, zoomInButton].forEach((button) => {
            if (button) {
                button.disabled = !ready;
            }
        });
        if (canvasHost) {
            canvasHost.dataset.live2dZoom = String(Math.round(stageLive2DZoom * 1000) / 1000);
            canvasHost.dataset.live2dOffsetX = String(Math.round(stageLive2DOffsetX * 100) / 100);
            canvasHost.dataset.live2dOffsetY = String(Math.round(stageLive2DOffsetY * 100) / 100);
        }
    }

    function markLive2DUnavailable(messageKey) {
        destroyLive2DApp();
        if (canvasHost) {
            canvasHost.dataset.live2d = "fallback";
            canvasHost.dataset.live2dSource = live2dConfig ? live2dConfig.source : "";
            canvasHost.dataset.live2dSelectionKey = live2dConfig ? live2dConfig.selection_key : "";
            canvasHost.dataset.live2dModelUrl = live2dConfig ? live2dConfig.model_url : "";
            canvasHost.dataset.i18nFallbackKey = messageKey;
            canvasHost.textContent = i18n.t(messageKey);
        }
        onStatus?.(messageKey);
    }

    return {
        adjustZoom,
        applyMouthValue,
        applyVisualState,
        canAdjustView,
        canAdjustZoom,
        destroy,
        getConfig,
        getKey,
        getView,
        getZoom,
        init,
        persistView,
        refreshLocalizedText,
        reloadFromContext,
        resetZoom,
        setOffsets,
        setZoom,
    };
}


function clampNumber(value, min, max, fallback) {
    const number = Number.parseFloat(String(value));
    if (!Number.isFinite(number)) {
        return fallback;
    }
    return clamp(number, min, max);
}


function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

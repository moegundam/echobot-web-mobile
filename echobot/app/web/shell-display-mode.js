const DISPLAY_MODE_STORAGE_KEY = "echobot.shell.displayMode";
const DEFAULT_DISPLAY_MODE = "auto";
const PHONE_VIEWPORT_MAX_WIDTH = 699;
const TABLET_VIEWPORT_MAX_WIDTH = 1023;

const DISPLAY_MODES = [
    { code: "auto", labelKey: "displayMode.auto" },
    { code: "mobile", labelKey: "displayMode.mobile" },
    { code: "portrait", labelKey: "displayMode.portrait" },
    { code: "landscape", labelKey: "displayMode.landscape" },
    { code: "desktop", labelKey: "displayMode.desktop" },
];

export function initShellDisplayMode({ t } = {}) {
    const controller = {
        selectedMode: resolveInitialMode(),
        effectiveMode: "portrait",
        refresh() {
            renderDisplayModeSwitchers(controller, t);
        },
        apply() {
            applyDisplayMode(controller);
        },
    };

    renderDisplayModeSwitchers(controller, t);
    applyDisplayMode(controller);
    bindViewportUpdates(controller);
    return controller;
}

function resolveInitialMode() {
    const storedMode = readStoredMode();
    return isSupportedMode(storedMode) ? storedMode : DEFAULT_DISPLAY_MODE;
}

function readStoredMode() {
    try {
        return String(window.localStorage.getItem(DISPLAY_MODE_STORAGE_KEY) || "");
    } catch (_error) {
        return "";
    }
}

function writeStoredMode(mode) {
    try {
        window.localStorage.setItem(DISPLAY_MODE_STORAGE_KEY, mode);
    } catch (_error) {
        // localStorage can be unavailable in restricted browsing contexts.
    }
}

function isSupportedMode(mode) {
    return DISPLAY_MODES.some((item) => item.code === mode);
}

function renderDisplayModeSwitchers(controller, t) {
    const containers = Array.from(document.querySelectorAll("[data-display-mode-switcher]"));
    containers.forEach((container) => {
        const label = document.createElement("label");
        label.className = "shell-display-mode-select-label";

        const labelText = document.createElement("span");
        labelText.textContent = translate(t, "displayMode.label");

        const select = document.createElement("select");
        select.className = "shell-display-mode-select";
        select.setAttribute("aria-label", translate(t, "displayMode.label"));

        DISPLAY_MODES.forEach((mode) => {
            const option = document.createElement("option");
            option.value = mode.code;
            option.textContent = translate(t, mode.labelKey);
            select.appendChild(option);
        });

        select.value = controller.selectedMode;
        select.addEventListener("change", () => {
            const nextMode = isSupportedMode(select.value) ? select.value : DEFAULT_DISPLAY_MODE;
            controller.selectedMode = nextMode;
            writeStoredMode(nextMode);
            applyDisplayMode(controller);
            renderDisplayModeSwitchers(controller, t);
        });

        label.append(labelText, select);
        container.replaceChildren(label);
    });
}

function applyDisplayMode(controller) {
    const viewport = currentViewport();
    const detectedMode = detectMode(viewport);
    const effectiveMode = controller.selectedMode === "auto"
        ? detectedMode
        : controller.selectedMode;
    const compactViewport = viewportClass(viewport) !== "desktop";
    controller.effectiveMode = effectiveMode;

    const targets = [document.documentElement, document.body].filter(Boolean);
    targets.forEach((target) => {
        target.dataset.displayMode = controller.selectedMode;
        target.dataset.effectiveDisplayMode = effectiveMode;
        target.dataset.deviceClass = compactViewport || viewport.mobileDevice ? "mobile" : "desktop";
        target.dataset.inputMode = viewport.coarsePointer ? "touch" : "pointer";
        target.dataset.viewportOrientation = viewport.width >= viewport.height
            ? "landscape"
            : "portrait";
        target.dataset.viewportClass = viewportClass(viewport);
    });
}

function currentViewport() {
    const width = Math.max(window.innerWidth || 0, 1);
    const height = Math.max(window.innerHeight || 0, 1);
    const coarsePointer = window.matchMedia
        ? window.matchMedia("(pointer: coarse)").matches
        : false;
    const userAgent = String(window.navigator && window.navigator.userAgent || "");
    const maxTouchPoints = Number(window.navigator && window.navigator.maxTouchPoints || 0);
    return {
        width,
        height,
        coarsePointer,
        mobileDevice: (
            coarsePointer
            || maxTouchPoints > 0
            || /Android|iPhone|iPad|iPod|Mobile|Windows Phone/i.test(userAgent)
        ),
    };
}

function detectMode(viewport) {
    const viewportMode = viewportClass(viewport);
    if (!viewport.mobileDevice && viewportMode === "desktop") {
        return "desktop";
    }
    return viewport.width >= viewport.height ? "landscape" : "portrait";
}

function viewportClass(viewport) {
    if (viewport.width > TABLET_VIEWPORT_MAX_WIDTH) {
        return "desktop";
    }
    if (viewport.width > PHONE_VIEWPORT_MAX_WIDTH) {
        return "tablet";
    }
    return "phone";
}

function bindViewportUpdates(controller) {
    let frameId = 0;
    const scheduleApply = () => {
        if (frameId) {
            return;
        }
        frameId = window.requestAnimationFrame(() => {
            frameId = 0;
            applyDisplayMode(controller);
        });
    };

    window.addEventListener("resize", scheduleApply, { passive: true });
    window.addEventListener("orientationchange", scheduleApply, { passive: true });
}

function translate(t, key) {
    if (typeof t === "function") {
        return t(key);
    }
    const fallback = {
        "displayMode.label": "Display",
        "displayMode.auto": "Auto",
        "displayMode.mobile": "Mobile",
        "displayMode.portrait": "Portrait",
        "displayMode.landscape": "Landscape",
        "displayMode.desktop": "Desktop / Dense",
    };
    return fallback[key] || key;
}

const DISPLAY_MODE_STORAGE_KEY = "echobot.shell.displayMode";
const DEFAULT_DISPLAY_MODE = "auto";
const PHONE_VIEWPORT_MAX_WIDTH = 699;
const TABLET_VIEWPORT_MAX_WIDTH = 1023;

const DISPLAY_MODES = [
    { code: "auto", labelKey: "displayMode.auto" },
    { code: "mobile", labelKey: "displayMode.mobile" },
    { code: "tablet", labelKey: "displayMode.tablet" },
    { code: "desktop", labelKey: "displayMode.desktop" },
];
const LEGACY_DISPLAY_MODE_MAP = {
    portrait: "mobile",
    landscape: "tablet",
};

export function initShellDisplayMode({ t } = {}) {
    const controller = {
        selectedMode: resolveInitialMode(),
        effectiveMode: "mobile",
        layoutMode: "mobile",
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
    return normalizeMode(storedMode);
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

function normalizeMode(mode) {
    const normalizedMode = String(mode || "").trim();
    if (isSupportedMode(normalizedMode)) {
        return normalizedMode;
    }
    return LEGACY_DISPLAY_MODE_MAP[normalizedMode] || DEFAULT_DISPLAY_MODE;
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
        select.name = "echobot-display-mode";
        select.setAttribute("aria-label", translate(t, "displayMode.label"));

        DISPLAY_MODES.forEach((mode) => {
            const option = document.createElement("option");
            option.value = mode.code;
            option.textContent = translate(t, mode.labelKey);
            select.appendChild(option);
        });

        select.value = controller.selectedMode;
        select.addEventListener("change", () => {
            const nextMode = normalizeMode(select.value);
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
    const requestedMode = normalizeMode(controller.selectedMode);
    const layoutMode = resolveLayoutMode(requestedMode, detectedMode, viewport);
    const viewportSizeClass = viewportClass(viewport);
    const deviceClass = detectedDeviceClass(viewport);
    controller.effectiveMode = layoutMode;
    controller.layoutMode = layoutMode;

    const targets = [document.documentElement, document.body].filter(Boolean);
    targets.forEach((target) => {
        target.dataset.displayMode = requestedMode;
        target.dataset.requestedDisplayMode = requestedMode;
        target.dataset.effectiveDisplayMode = layoutMode;
        target.dataset.layoutMode = layoutMode;
        target.dataset.deviceClass = deviceClass;
        target.dataset.inputMode = viewport.coarsePointer ? "touch" : "pointer";
        target.dataset.viewportOrientation = viewport.width >= viewport.height
            ? "landscape"
            : "portrait";
        target.dataset.viewportClass = viewportSizeClass;
    });
}

function resolveLayoutMode(requestedMode, detectedMode, viewport) {
    const deviceClass = detectedDeviceClass(viewport);
    if (requestedMode === "auto") {
        return detectedMode;
    }
    if (deviceClass === "phone") {
        return requestedMode === "mobile" ? "mobile" : detectedMode;
    }
    if (deviceClass === "tablet" && requestedMode === "desktop") {
        return "tablet";
    }
    return requestedMode;
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
    const deviceClass = detectedDeviceClass(viewport);
    if (deviceClass === "desktop") {
        return "desktop";
    }
    if (deviceClass === "tablet") {
        return "tablet";
    }
    return "mobile";
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

function detectedDeviceClass(viewport) {
    if (!viewport.mobileDevice) {
        return "desktop";
    }
    if (viewportClass(viewport) === "phone") {
        return "phone";
    }
    return "tablet";
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
        "displayMode.tablet": "Tablet",
        "displayMode.desktop": "Desktop / Dense",
    };
    return fallback[key] || key;
}

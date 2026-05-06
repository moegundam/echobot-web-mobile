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
let displayModeMenuCounter = 0;
let displayModeMenuGlobalEventsBound = false;

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
    bindDisplayModeMenuGlobalEvents();
    containers.forEach((container) => {
        const label = document.createElement("div");
        label.className = "shell-display-mode-select-label";

        const labelText = document.createElement("span");
        labelText.textContent = translate(t, "displayMode.label");

        const picker = document.createElement("div");
        picker.className = "shell-display-mode-picker";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "shell-display-mode-select";
        button.setAttribute("aria-haspopup", "listbox");
        button.setAttribute("aria-expanded", "false");

        const value = document.createElement("span");
        value.className = "shell-display-mode-select-value";

        const chevron = document.createElement("span");
        chevron.className = "shell-display-mode-select-chevron";
        chevron.setAttribute("aria-hidden", "true");
        chevron.textContent = "v";

        const menuId = `shell-display-mode-menu-${++displayModeMenuCounter}`;
        const menu = document.createElement("div");
        menu.id = menuId;
        menu.className = "shell-display-mode-menu";
        menu.setAttribute("role", "listbox");
        menu.hidden = true;
        button.setAttribute("aria-controls", menuId);

        DISPLAY_MODES.forEach((mode) => {
            const option = document.createElement("button");
            option.type = "button";
            option.className = "shell-display-mode-option";
            option.dataset.displayModeCode = mode.code;
            option.setAttribute("role", "option");
            option.textContent = translate(t, mode.labelKey);
            option.addEventListener("click", () => {
                setDisplayMode(controller, mode.code, t);
            });
            option.addEventListener("keydown", (event) => {
                handleDisplayModeOptionKeydown(event, picker, option);
            });
            menu.appendChild(option);
        });

        button.append(value, chevron);
        button.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            toggleDisplayModeMenu(picker);
        });
        button.addEventListener("keydown", (event) => {
            if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openDisplayModeMenu(picker);
            }
            if (event.key === "Escape") {
                closeDisplayModeMenu(picker);
            }
        });
        menu.addEventListener("click", (event) => {
            event.stopPropagation();
        });

        picker.append(button, menu);
        label.append(labelText, picker);
        container.replaceChildren(label);
    });
    syncDisplayModeSwitchers(controller, t);
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

function setDisplayMode(controller, mode, t) {
    const nextMode = normalizeMode(mode);
    controller.selectedMode = nextMode;
    writeStoredMode(nextMode);
    applyDisplayMode(controller);
    renderDisplayModeSwitchers(controller, t);
}

function bindDisplayModeMenuGlobalEvents() {
    if (displayModeMenuGlobalEventsBound) {
        return;
    }
    displayModeMenuGlobalEventsBound = true;
    document.addEventListener("click", () => {
        closeAllDisplayModeMenus();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeAllDisplayModeMenus();
        }
    });
}

function toggleDisplayModeMenu(picker) {
    const button = picker.querySelector(".shell-display-mode-select");
    const isOpen = button && button.getAttribute("aria-expanded") === "true";
    if (isOpen) {
        closeDisplayModeMenu(picker);
        return;
    }
    openDisplayModeMenu(picker);
}

function openDisplayModeMenu(picker) {
    closeAllDisplayModeMenus(picker);
    const button = picker.querySelector(".shell-display-mode-select");
    const menu = picker.querySelector(".shell-display-mode-menu");
    if (!button || !menu) {
        return;
    }
    picker.classList.add("is-open");
    button.setAttribute("aria-expanded", "true");
    menu.hidden = false;
    queueMicrotask(() => {
        const selectedOption = menu.querySelector('.shell-display-mode-option[aria-selected="true"]')
            || menu.querySelector(".shell-display-mode-option");
        if (selectedOption) {
            selectedOption.focus();
        }
    });
}

function closeDisplayModeMenu(picker) {
    const button = picker.querySelector(".shell-display-mode-select");
    const menu = picker.querySelector(".shell-display-mode-menu");
    picker.classList.remove("is-open");
    if (button) {
        button.setAttribute("aria-expanded", "false");
    }
    if (menu) {
        menu.hidden = true;
    }
}

function closeAllDisplayModeMenus(exceptPicker = null) {
    document.querySelectorAll(".shell-display-mode-picker.is-open").forEach((picker) => {
        if (picker !== exceptPicker) {
            closeDisplayModeMenu(picker);
        }
    });
}

function handleDisplayModeOptionKeydown(event, picker, option) {
    if (event.key === "Escape") {
        event.preventDefault();
        closeDisplayModeMenu(picker);
        const button = picker.querySelector(".shell-display-mode-select");
        if (button) {
            button.focus();
        }
        return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Home" && event.key !== "End") {
        return;
    }
    event.preventDefault();
    const options = Array.from(picker.querySelectorAll(".shell-display-mode-option"));
    const currentIndex = options.indexOf(option);
    let nextIndex = currentIndex;
    if (event.key === "ArrowDown") {
        nextIndex = currentIndex >= options.length - 1 ? 0 : currentIndex + 1;
    }
    if (event.key === "ArrowUp") {
        nextIndex = currentIndex <= 0 ? options.length - 1 : currentIndex - 1;
    }
    if (event.key === "Home") {
        nextIndex = 0;
    }
    if (event.key === "End") {
        nextIndex = options.length - 1;
    }
    if (options[nextIndex]) {
        options[nextIndex].focus();
    }
}

function syncDisplayModeSwitchers(controller, t) {
    const modeConfig = DISPLAY_MODES.find((item) => item.code === controller.selectedMode) || DISPLAY_MODES[0];
    const modeLabel = translate(t, modeConfig.labelKey);
    document.querySelectorAll(".shell-display-mode-picker").forEach((picker) => {
        const button = picker.querySelector(".shell-display-mode-select");
        const value = picker.querySelector(".shell-display-mode-select-value");
        if (value) {
            value.textContent = modeLabel;
        }
        if (button) {
            button.dataset.displayModeCode = modeConfig.code;
            button.setAttribute("aria-label", `${translate(t, "displayMode.label")}: ${modeLabel}`);
        }
        picker.querySelectorAll(".shell-display-mode-option").forEach((option) => {
            const selected = option.dataset.displayModeCode === modeConfig.code;
            option.classList.toggle("is-selected", selected);
            option.setAttribute("aria-selected", selected ? "true" : "false");
        });
    });
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

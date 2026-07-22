const STAGE_SUBTITLE_STORAGE_KEY = "echobot.stage.subtitles.hidden";
const STAGE_CONTROLS_AUTO_HIDE_STORAGE_KEY = "echobot.stage.controls.auto-hide";
const STAGE_CONTROLS_IDLE_DELAY_MS = 6000;


export function createStageMenuController({
    elements,
    i18n,
    onZoomKeyDown,
}) {
    const {
        subtitlePanel,
        subtitleToggleButton,
        menuToggleButton,
        menuCloseButton,
        menuBackdrop,
        menuPanel,
        stageToolbar,
        stageSurface,
        canvasHost,
        fullscreenToggleButton,
        controlsAutoHideCheckbox,
    } = elements;
    let subtitlesHidden = readStoredSubtitlesHidden();
    let stageControlsAutoHide = readStoredControlsAutoHide();
    let stageControlsIdleTimer = null;
    let stageMenuPreviousFocus = null;

    function isStageMenuOpen() {
        return Boolean(menuPanel && menuPanel.getAttribute("aria-hidden") === "false");
    }

    function setStageMenuInert(open) {
        [stageToolbar, canvasHost, subtitlePanel].forEach((element) => {
            if (element) {
                element.inert = open;
            }
        });
    }

    function getStageMenuFocusableElements() {
        if (!menuPanel) {
            return [];
        }
        return Array.from(menuPanel.querySelectorAll(
            "button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
        )).filter((element) => (
            !element.hidden
            && !element.closest("[hidden], [aria-hidden='true']")
            && element.getAttribute("aria-hidden") !== "true"
        ));
    }

    function focusStageMenu() {
        const focusableElements = getStageMenuFocusableElements();
        const target = menuCloseButton && !menuCloseButton.disabled
            ? menuCloseButton
            : focusableElements[0];
        target?.focus({ preventScroll: true });
    }

    function trapStageMenuFocus(event) {
        const focusableElements = getStageMenuFocusableElements();
        if (focusableElements.length === 0) {
            event.preventDefault();
            menuPanel?.focus({ preventScroll: true });
            return;
        }

        const first = focusableElements[0];
        const last = focusableElements[focusableElements.length - 1];
        const activeElement = document.activeElement;
        if (!menuPanel || !menuPanel.contains(activeElement)) {
            event.preventDefault();
            first.focus({ preventScroll: true });
            return;
        }
        if (event.shiftKey && activeElement === first) {
            event.preventDefault();
            last.focus({ preventScroll: true });
        } else if (!event.shiftKey && activeElement === last) {
            event.preventDefault();
            first.focus({ preventScroll: true });
        }
    }

    function restoreStageMenuFocus() {
        const previousFocus = stageMenuPreviousFocus;
        stageMenuPreviousFocus = null;
        if (
            previousFocus
            && previousFocus.isConnected
            && previousFocus !== document.body
            && previousFocus !== document.documentElement
            && !previousFocus.inert
            && !menuPanel?.contains(previousFocus)
        ) {
            previousFocus.focus({ preventScroll: true });
            return;
        }
        menuToggleButton?.focus({ preventScroll: true });
    }

    function setStageMenuOpen(isOpen, options = {}) {
        const open = Boolean(isOpen);
        const wasOpen = isStageMenuOpen();
        if (open && !wasOpen) {
            stageMenuPreviousFocus = document.activeElement;
        }
        if (menuPanel) {
            menuPanel.setAttribute("aria-hidden", open ? "false" : "true");
        }
        if (menuToggleButton) {
            menuToggleButton.setAttribute("aria-expanded", open ? "true" : "false");
            menuToggleButton.textContent = i18n.t(open ? "stage.menu.close" : "stage.menu.open");
        }
        if (menuBackdrop) {
            menuBackdrop.hidden = !open;
        }
        setStageMenuInert(open);
        document.documentElement.classList.toggle("stage-menu-open", open);
        if (open) {
            revealStageControls({ schedule: false });
            focusStageMenu();
            window.setTimeout(() => {
                if (isStageMenuOpen()) {
                    focusStageMenu();
                }
            }, 0);
        } else if (options.restoreFocus !== false) {
            restoreStageMenuFocus();
        }
        if (!open) {
            scheduleStageControlsAutoHide();
        }
    }

    function setSubtitlesHidden(hidden, options = {}) {
        subtitlesHidden = Boolean(hidden);
        if (subtitlePanel) {
            subtitlePanel.hidden = subtitlesHidden;
        }
        if (subtitleToggleButton) {
            subtitleToggleButton.setAttribute("aria-pressed", subtitlesHidden ? "true" : "false");
            subtitleToggleButton.textContent = i18n.t(
                subtitlesHidden ? "stage.subtitle.show" : "stage.subtitle.hide",
            );
        }
        document.documentElement.classList.toggle("stage-subtitles-hidden", subtitlesHidden);
        if (options.persist !== false) {
            writeStoredSubtitlesHidden(subtitlesHidden);
        }
    }

    function bind() {
        subtitleToggleButton?.addEventListener("click", () => {
            setSubtitlesHidden(!subtitlesHidden);
        });
        menuToggleButton?.addEventListener("click", () => {
            setStageMenuOpen(true);
        });
        menuCloseButton?.addEventListener("click", () => {
            setStageMenuOpen(false);
        });
        menuBackdrop?.addEventListener("click", () => {
            setStageMenuOpen(false);
        });
        fullscreenToggleButton?.addEventListener("click", () => {
            void toggleStageFullscreen();
        });
        controlsAutoHideCheckbox?.addEventListener("change", () => {
            setStageControlsAutoHide(controlsAutoHideCheckbox.checked);
        });
        stageSurface?.addEventListener("pointerdown", revealStageControls);
        stageSurface?.addEventListener("pointermove", revealStageControls);
        stageToolbar?.addEventListener("focusin", revealStageControls);
        stageToolbar?.addEventListener("focusout", scheduleStageControlsAutoHide);
        document.addEventListener("fullscreenchange", handleFullscreenChange);
        document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
        document.addEventListener("visibilitychange", handleVisibilityChange);
        window.addEventListener("keydown", handleKeydown);
        setStageControlsAutoHide(stageControlsAutoHide, { persist: false });
        refreshFullscreenButton();
    }

    function handleKeydown(event) {
        revealStageControls();
        if (event.key === "Escape" && isStageMenuOpen()) {
            setStageMenuOpen(false);
            return;
        }
        if (event.key === "Tab" && isStageMenuOpen()) {
            trapStageMenuFocus(event);
            return;
        }
        onZoomKeyDown?.(event);
    }

    function refreshLocalizedText() {
        setSubtitlesHidden(subtitlesHidden, { persist: false });
        if (menuToggleButton) {
            menuToggleButton.textContent = i18n.t(
                isStageMenuOpen() ? "stage.menu.close" : "stage.menu.open",
            );
        }
        refreshFullscreenButton();
    }

    function readStoredSubtitlesHidden() {
        try {
            return window.localStorage.getItem(STAGE_SUBTITLE_STORAGE_KEY) === "1";
        } catch (_error) {
            return false;
        }
    }

    function writeStoredSubtitlesHidden(hidden) {
        try {
            window.localStorage.setItem(STAGE_SUBTITLE_STORAGE_KEY, hidden ? "1" : "0");
        } catch (_error) {
            // Subtitle visibility is still applied when storage is unavailable.
        }
    }

    function setStageControlsAutoHide(enabled, options = {}) {
        stageControlsAutoHide = Boolean(enabled);
        if (controlsAutoHideCheckbox) {
            controlsAutoHideCheckbox.checked = stageControlsAutoHide;
        }
        document.documentElement.classList.toggle(
            "stage-controls-auto-hide-enabled",
            stageControlsAutoHide,
        );
        if (options.persist !== false) {
            writeStoredControlsAutoHide(stageControlsAutoHide);
        }
        revealStageControls();
    }

    function revealStageControls(options = {}) {
        clearStageControlsIdleTimer();
        document.documentElement.classList.remove("stage-controls-auto-hidden");
        if (options.schedule !== false) {
            scheduleStageControlsAutoHide();
        }
    }

    function scheduleStageControlsAutoHide() {
        clearStageControlsIdleTimer();
        if (
            !stageControlsAutoHide
            || isStageMenuOpen()
            || document.visibilityState === "hidden"
        ) {
            return;
        }
        stageControlsIdleTimer = window.setTimeout(() => {
            if (stageToolbar?.contains(document.activeElement)) {
                scheduleStageControlsAutoHide();
                return;
            }
            document.documentElement.classList.add("stage-controls-auto-hidden");
        }, STAGE_CONTROLS_IDLE_DELAY_MS);
    }

    function clearStageControlsIdleTimer() {
        if (stageControlsIdleTimer !== null) {
            window.clearTimeout(stageControlsIdleTimer);
            stageControlsIdleTimer = null;
        }
    }

    function handleVisibilityChange() {
        if (document.visibilityState === "hidden") {
            clearStageControlsIdleTimer();
            return;
        }
        revealStageControls();
    }

    async function toggleStageFullscreen() {
        const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
        try {
            if (fullscreenElement) {
                const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
                await exitFullscreen?.call(document);
            } else {
                const requestFullscreen = stageSurface?.requestFullscreen
                    || stageSurface?.webkitRequestFullscreen;
                if (!requestFullscreen) {
                    fullscreenToggleButton.disabled = true;
                    fullscreenToggleButton.title = i18n.t("stage.fullscreenUnavailable");
                    return;
                }
                await requestFullscreen.call(stageSurface);
            }
        } catch (error) {
            console.warn("Unable to toggle Stage full screen", error);
            fullscreenToggleButton.title = i18n.t("stage.fullscreenUnavailable");
        } finally {
            refreshFullscreenButton();
        }
    }

    function handleFullscreenChange() {
        refreshFullscreenButton();
        revealStageControls();
    }

    function refreshFullscreenButton() {
        if (!fullscreenToggleButton) {
            return;
        }
        const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
        const key = fullscreenElement ? "stage.exitFullscreen" : "stage.fullscreen";
        fullscreenToggleButton.textContent = i18n.t(key);
        fullscreenToggleButton.dataset.i18nKey = key;
        fullscreenToggleButton.setAttribute("aria-pressed", fullscreenElement ? "true" : "false");
    }

    function readStoredControlsAutoHide() {
        try {
            return window.localStorage.getItem(STAGE_CONTROLS_AUTO_HIDE_STORAGE_KEY) !== "0";
        } catch (_error) {
            return true;
        }
    }

    function writeStoredControlsAutoHide(enabled) {
        try {
            window.localStorage.setItem(
                STAGE_CONTROLS_AUTO_HIDE_STORAGE_KEY,
                enabled ? "1" : "0",
            );
        } catch (_error) {
            // Auto-hide remains active for this page when storage is unavailable.
        }
    }

    return {
        bind,
        getSubtitlesHidden: () => subtitlesHidden,
        isStageMenuOpen,
        refreshLocalizedText,
        setStageMenuOpen,
        setStageControlsAutoHide,
        setSubtitlesHidden,
    };
}

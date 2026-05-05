import { DOM } from "../../core/dom.js";
import { readBoolean, readString, writeBoolean } from "../../core/storage.js";

const SETTINGS_PANEL_STORAGE_KEY = "echobot.web.settings_panel_open";
const CRON_PANEL_STORAGE_KEY = "echobot.web.cron_panel_open";
const HEARTBEAT_PANEL_STORAGE_KEY = "echobot.web.heartbeat_panel_open";
const LIVE2D_PANEL_STORAGE_KEY = "echobot.web.live2d_panel_open";
const RUNTIME_PANEL_STORAGE_KEY = "echobot.web.runtime_panel_open";
const STAGE_BACKGROUND_PANEL_STORAGE_KEY = "echobot.web.stage_background_panel_open";
const STAGE_EFFECTS_PANEL_STORAGE_KEY = "echobot.web.stage_effects_panel_open";

export function createPanelController(deps) {
    const { handleCronPanelToggle, handleHeartbeatPanelToggle } = deps;

    function isSettingsPanelOpen() {
        return !DOM.settingsPanel || DOM.settingsPanel.open;
    }

    function restoreSettingsPanelState() {
        if (!DOM.settingsPanel) {
            return;
        }

        const storedState = readString(SETTINGS_PANEL_STORAGE_KEY, "");
        DOM.settingsPanel.open = storedState === ""
            ? shouldDefaultSettingsPanelOpen()
            : storedState === "true";
    }

    function handleSettingsPanelToggle() {
        if (DOM.settingsPanel) {
            writeBoolean(SETTINGS_PANEL_STORAGE_KEY, DOM.settingsPanel.open);
        }
        handleCronPanelToggle();
        handleHeartbeatPanelToggle();
    }

    function restoreCronPanelState() {
        if (!DOM.cronPanel) {
            return;
        }

        DOM.cronPanel.open = readBoolean(CRON_PANEL_STORAGE_KEY, false);
    }

    function restoreHeartbeatPanelState() {
        if (!DOM.heartbeatPanel) {
            return;
        }

        DOM.heartbeatPanel.open = readBoolean(HEARTBEAT_PANEL_STORAGE_KEY, false);
    }

    function restoreRuntimePanelState() {
        if (!DOM.runtimePanel) {
            return;
        }

        DOM.runtimePanel.open = readBoolean(RUNTIME_PANEL_STORAGE_KEY, true);
    }

    function restoreStageBackgroundPanelState() {
        if (!DOM.stageBackgroundPanel) {
            return;
        }

        DOM.stageBackgroundPanel.open = readBoolean(STAGE_BACKGROUND_PANEL_STORAGE_KEY, true);
    }

    function restoreLive2DPanelState() {
        if (!DOM.live2dPanel) {
            return;
        }

        DOM.live2dPanel.open = readBoolean(LIVE2D_PANEL_STORAGE_KEY, true);
    }

    function restoreStageEffectsPanelState() {
        if (!DOM.stageEffectsPanel) {
            return;
        }

        DOM.stageEffectsPanel.open = readBoolean(STAGE_EFFECTS_PANEL_STORAGE_KEY, true);
    }

    function handleStageEffectsPanelToggle() {
        if (DOM.stageEffectsPanel) {
            writeBoolean(STAGE_EFFECTS_PANEL_STORAGE_KEY, DOM.stageEffectsPanel.open);
        }
    }

    function handleRuntimePanelToggle() {
        if (DOM.runtimePanel) {
            writeBoolean(RUNTIME_PANEL_STORAGE_KEY, DOM.runtimePanel.open);
        }
    }

    function handleStageBackgroundPanelToggle() {
        if (DOM.stageBackgroundPanel) {
            writeBoolean(STAGE_BACKGROUND_PANEL_STORAGE_KEY, DOM.stageBackgroundPanel.open);
        }
    }

    function handleLive2DPanelToggle() {
        if (DOM.live2dPanel) {
            writeBoolean(LIVE2D_PANEL_STORAGE_KEY, DOM.live2dPanel.open);
        }
    }

    function shouldDefaultSettingsPanelOpen() {
        return window.matchMedia
            ? window.matchMedia("(min-width: 900px) and (orientation: landscape)").matches
            : true;
    }

    return {
        handleLive2DPanelToggle,
        handleRuntimePanelToggle,
        handleSettingsPanelToggle,
        handleStageBackgroundPanelToggle,
        handleStageEffectsPanelToggle,
        isSettingsPanelOpen,
        restoreCronPanelState,
        restoreHeartbeatPanelState,
        restoreLive2DPanelState,
        restoreRuntimePanelState,
        restoreSettingsPanelState,
        restoreStageBackgroundPanelState,
        restoreStageEffectsPanelState,
    };
}

export function writeCronPanelState(isOpen) {
    writeBoolean(CRON_PANEL_STORAGE_KEY, isOpen);
}

export function writeHeartbeatPanelState(isOpen) {
    writeBoolean(HEARTBEAT_PANEL_STORAGE_KEY, isOpen);
}

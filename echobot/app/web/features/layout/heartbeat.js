import { DOM } from "../../core/dom.js";
import { panelState } from "../../core/store.js";
import { writeHeartbeatPanelState } from "./panels.js";

export function createHeartbeatController(deps) {
    const { isSettingsPanelOpen, requestJson } = deps;
    const t = typeof deps.t === "function" ? deps.t : (key, params = {}) => {
        return String(key).replace(/\{([A-Za-z0-9_]+)\}/g, (_match, name) => {
            return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : "";
        });
    };

    function handleHeartbeatPanelToggle() {
        if (!DOM.heartbeatPanel || !DOM.heartbeatSummaryText) {
            return;
        }

        const isExpanded = DOM.heartbeatPanel.open;
        const settingsPanelOpen = isSettingsPanelOpen();
        writeHeartbeatPanelState(isExpanded);

        if (!isExpanded) {
            DOM.heartbeatSummaryText.textContent = panelState.heartbeatDirty
                ? t("console.unsavedChanges")
                : t("console.hidden");
            renderHeartbeatState();
            return;
        }

        if (!settingsPanelOpen) {
            DOM.heartbeatSummaryText.textContent = panelState.heartbeatDirty
                ? t("console.unsavedChanges")
                : t("console.expanded");
            renderHeartbeatState();
            return;
        }

        if (panelState.heartbeatLoaded || panelState.heartbeatDirty) {
            renderHeartbeatState();
            return;
        }

        DOM.heartbeatSummaryText.textContent = t("console.loadingEllipsis");
        void refreshHeartbeatPanel();
    }

    async function refreshHeartbeatPanel(options = {}) {
        if (
            !DOM.heartbeatPanel
            || !DOM.heartbeatPanel.open
            || !isSettingsPanelOpen()
            || panelState.heartbeatLoading
            || panelState.heartbeatSaving
        ) {
            return;
        }
        if (!options.force && panelState.heartbeatDirty) {
            renderHeartbeatState();
            return;
        }

        panelState.heartbeatLoading = true;
        updateHeartbeatControls();
        if (DOM.heartbeatStatus) {
            DOM.heartbeatStatus.textContent = t("console.heartbeatLoading");
        }

        try {
            const payload = await requestJson("/api/heartbeat");
            renderHeartbeatPanel(payload);
        } catch (error) {
            console.error(error);
            if (DOM.heartbeatSummaryText) {
                DOM.heartbeatSummaryText.textContent = t("console.loadFailed");
            }
            if (DOM.heartbeatStatus) {
                DOM.heartbeatStatus.textContent = error.message || t("console.heartbeatLoadFailed");
            }
        } finally {
            panelState.heartbeatLoading = false;
            updateHeartbeatControls();
        }
    }

    async function saveHeartbeat() {
        if (!DOM.heartbeatInput || panelState.heartbeatLoading || panelState.heartbeatSaving) {
            return;
        }

        panelState.heartbeatSaving = true;
        updateHeartbeatControls();
        if (DOM.heartbeatStatus) {
            DOM.heartbeatStatus.textContent = t("console.heartbeatSaving");
        }

        try {
            const payload = await requestJson("/api/heartbeat", {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    content: DOM.heartbeatInput.value,
                }),
            });
            renderHeartbeatPanel(payload);
        } catch (error) {
            console.error(error);
            if (DOM.heartbeatSummaryText) {
                DOM.heartbeatSummaryText.textContent = t("console.saveFailed");
            }
            if (DOM.heartbeatStatus) {
                DOM.heartbeatStatus.textContent = error.message || t("console.heartbeatSaveFailed");
            }
        } finally {
            panelState.heartbeatSaving = false;
            updateHeartbeatControls();
        }
    }

    function handleHeartbeatInputChange() {
        if (!DOM.heartbeatInput) {
            return;
        }

        panelState.heartbeatDirty = DOM.heartbeatInput.value !== panelState.heartbeatSavedContent;
        renderHeartbeatState();
    }

    function renderHeartbeatPanel(payload) {
        panelState.heartbeatData = payload || null;
        panelState.heartbeatLoaded = true;
        panelState.heartbeatSavedContent = String((payload && payload.content) || "");
        panelState.heartbeatDirty = false;

        if (DOM.heartbeatInput) {
            DOM.heartbeatInput.value = panelState.heartbeatSavedContent;
        }

        renderHeartbeatState();
    }

    function renderHeartbeatState() {
        const payload = panelState.heartbeatData;

        if (DOM.heartbeatSummaryText) {
            DOM.heartbeatSummaryText.textContent = buildHeartbeatSummaryText(payload);
        }
        if (DOM.heartbeatStatus) {
            DOM.heartbeatStatus.textContent = buildHeartbeatStatusText(payload);
        }
        if (DOM.heartbeatMeta) {
            DOM.heartbeatMeta.textContent = buildHeartbeatMetaText(payload);
        }

        updateHeartbeatControls();
    }

    function buildHeartbeatSummaryText(payload) {
        const isExpanded = Boolean(DOM.heartbeatPanel && DOM.heartbeatPanel.open);
        const settingsPanelOpen = isSettingsPanelOpen();

        if (panelState.heartbeatDirty) {
            return t("console.unsavedChanges");
        }
        if (!isExpanded) {
            return t("console.hidden");
        }
        if (!settingsPanelOpen) {
            return t("console.expanded");
        }
        if (!payload) {
            return t("console.loadAfterExpand");
        }
        if (!payload.enabled) {
            return payload.has_meaningful_content ? t("console.configuredDisabled") : t("console.disabled");
        }
        if (!payload.has_meaningful_content) {
            return t("console.noValidTasks");
        }
        return t("console.heartbeatIntervalSummary", { seconds: payload.interval_seconds || 0 });
    }

    function buildHeartbeatStatusText(payload) {
        if (!isSettingsPanelOpen()) {
            return t("console.heartbeatOpenSettingsFirst");
        }
        if (!payload) {
            return t("console.heartbeatLoadAfterExpand");
        }
        if (panelState.heartbeatDirty) {
            return t("console.heartbeatDirtyStatus");
        }

        const stateText = payload.enabled ? t("console.heartbeatRunning") : t("console.heartbeatDisabled");
        const contentText = payload.has_meaningful_content
            ? t("console.heartbeatHasTasks")
            : t("console.heartbeatNoTasks");
        return `${stateText} · ${contentText}`;
    }

    function buildHeartbeatMetaText(payload) {
        if (!payload) {
            return t("console.heartbeatMetaLoading");
        }
        return t("console.heartbeatIntervalMeta", { seconds: payload.interval_seconds || 0 });
    }

    function updateHeartbeatControls() {
        const isBusy = panelState.heartbeatLoading || panelState.heartbeatSaving;

        if (DOM.heartbeatInput) {
            DOM.heartbeatInput.disabled = isBusy;
        }
        if (DOM.heartbeatRefreshButton) {
            DOM.heartbeatRefreshButton.disabled = isBusy;
        }
        if (DOM.heartbeatSaveButton) {
            DOM.heartbeatSaveButton.disabled = isBusy || !panelState.heartbeatDirty;
        }
    }

    return {
        handleHeartbeatInputChange,
        handleHeartbeatPanelToggle,
        refreshHeartbeatPanel,
        refreshLocalizedText: renderHeartbeatState,
        saveHeartbeat,
    };
}

import { DOM } from "../../core/dom.js";
import { appState, runtimeState } from "../../core/store.js";

const DEFAULT_SHELL_SAFETY_MODE = "workspace-write";
const DEFAULT_RUNTIME_CONFIG = Object.freeze({
    delegated_ack_enabled: true,
    shell_safety_mode: DEFAULT_SHELL_SAFETY_MODE,
    file_write_enabled: true,
    cron_mutation_enabled: true,
    web_private_network_enabled: false,
});

const SHELL_SAFETY_MODE_LABEL_KEYS = {
    "danger-full-access": "console.shellSafetyFullAccess",
    "workspace-write": "console.shellSafetyWorkspaceWrite",
    "read-only": "console.shellSafetyReadOnly",
};

export function createRuntimeController(deps) {
    const {
        addMessage,
        requestJson,
        setRunStatus,
        t = (key, params = {}) => String(key).replace(/\{([A-Za-z0-9_]+)\}/g, (_match, name) => {
            return Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : "";
        }),
    } = deps;

    function currentRuntimeConfig() {
        return {
            delegated_ack_enabled: runtimeState.delegatedAckEnabled,
            shell_safety_mode: runtimeState.shellSafetyMode,
            file_write_enabled: runtimeState.fileWriteEnabled,
            cron_mutation_enabled: runtimeState.cronMutationEnabled,
            web_private_network_enabled: runtimeState.webPrivateNetworkEnabled,
        };
    }

    function normalizeRuntimeConfig(runtimeConfig) {
        return {
            delegated_ack_enabled: runtimeConfig
                ? runtimeConfig.delegated_ack_enabled !== false
                : DEFAULT_RUNTIME_CONFIG.delegated_ack_enabled,
            shell_safety_mode: runtimeConfig?.shell_safety_mode
                || DEFAULT_RUNTIME_CONFIG.shell_safety_mode,
            file_write_enabled: runtimeConfig
                ? runtimeConfig.file_write_enabled !== false
                : DEFAULT_RUNTIME_CONFIG.file_write_enabled,
            cron_mutation_enabled: runtimeConfig
                ? runtimeConfig.cron_mutation_enabled !== false
                : DEFAULT_RUNTIME_CONFIG.cron_mutation_enabled,
            web_private_network_enabled: runtimeConfig
                ? runtimeConfig.web_private_network_enabled === true
                : DEFAULT_RUNTIME_CONFIG.web_private_network_enabled,
        };
    }

    function applyRuntimeConfig(runtimeConfig) {
        const normalizedConfig = normalizeRuntimeConfig(runtimeConfig);
        runtimeState.delegatedAckEnabled = normalizedConfig.delegated_ack_enabled;
        runtimeState.shellSafetyMode = normalizedConfig.shell_safety_mode;
        runtimeState.fileWriteEnabled = normalizedConfig.file_write_enabled;
        runtimeState.cronMutationEnabled = normalizedConfig.cron_mutation_enabled;
        runtimeState.webPrivateNetworkEnabled = normalizedConfig.web_private_network_enabled;

        if (DOM.delegatedAckCheckbox) {
            DOM.delegatedAckCheckbox.checked = runtimeState.delegatedAckEnabled;
        }
        if (DOM.shellSafetyModeSelect) {
            DOM.shellSafetyModeSelect.value = runtimeState.shellSafetyMode;
        }
        if (DOM.fileWriteEnabledCheckbox) {
            DOM.fileWriteEnabledCheckbox.checked = runtimeState.fileWriteEnabled;
        }
        if (DOM.cronMutationEnabledCheckbox) {
            DOM.cronMutationEnabledCheckbox.checked = runtimeState.cronMutationEnabled;
        }
        if (DOM.webPrivateNetworkEnabledCheckbox) {
            DOM.webPrivateNetworkEnabledCheckbox.checked = runtimeState.webPrivateNetworkEnabled;
        }
        updateRuntimeControls();
    }

    async function handleRuntimeCheckboxToggle(options) {
        const {
            element,
            key,
            currentValue,
            enabledKey,
            disabledKey,
            settingKey,
        } = options;
        if (!element || runtimeState.runtimeConfigLoading) {
            return;
        }

        const nextValue = Boolean(element.checked);
        if (nextValue === currentValue) {
            updateRuntimeControls();
            return;
        }

        await saveRuntimeConfig(
            { [key]: nextValue },
            nextValue ? enabledKey : disabledKey,
            settingKey,
        );
    }

    async function handleDelegatedAckToggle() {
        await handleRuntimeCheckboxToggle({
            element: DOM.delegatedAckCheckbox,
            key: "delegated_ack_enabled",
            currentValue: runtimeState.delegatedAckEnabled,
            enabledKey: "console.runtime.taskNoticeEnabled",
            disabledKey: "console.runtime.taskNoticeDisabled",
            settingKey: "console.runtime.taskNotice",
        });
    }

    async function handleShellSafetyModeChange() {
        if (!DOM.shellSafetyModeSelect || runtimeState.runtimeConfigLoading) {
            return;
        }

        const nextValue = String(DOM.shellSafetyModeSelect.value || "").trim();
        if (!nextValue || nextValue === runtimeState.shellSafetyMode) {
            updateRuntimeControls();
            return;
        }

        await saveRuntimeConfig(
            { shell_safety_mode: nextValue },
            "console.runtime.shellSafetyModeSet",
            "console.runtime.shellSafetyMode",
            { mode: formatShellSafetyModeLabel(nextValue) },
        );
    }

    async function handleFileWriteToggle() {
        await handleRuntimeCheckboxToggle({
            element: DOM.fileWriteEnabledCheckbox,
            key: "file_write_enabled",
            currentValue: runtimeState.fileWriteEnabled,
            enabledKey: "console.runtime.fileWriteEnabled",
            disabledKey: "console.runtime.fileWriteDisabled",
            settingKey: "console.runtime.fileWrite",
        });
    }

    async function handleCronMutationToggle() {
        await handleRuntimeCheckboxToggle({
            element: DOM.cronMutationEnabledCheckbox,
            key: "cron_mutation_enabled",
            currentValue: runtimeState.cronMutationEnabled,
            enabledKey: "console.runtime.cronMutationEnabled",
            disabledKey: "console.runtime.cronMutationDisabled",
            settingKey: "console.runtime.cronMutation",
        });
    }

    async function handleWebPrivateNetworkToggle() {
        await handleRuntimeCheckboxToggle({
            element: DOM.webPrivateNetworkEnabledCheckbox,
            key: "web_private_network_enabled",
            currentValue: runtimeState.webPrivateNetworkEnabled,
            enabledKey: "console.runtime.privateNetworkEnabled",
            disabledKey: "console.runtime.privateNetworkDisabled",
            settingKey: "console.runtime.privateNetwork",
        });
    }

    async function handleRuntimeReset() {
        if (runtimeState.runtimeConfigLoading) {
            return;
        }
        await resetRuntimeConfig();
    }

    async function saveRuntimeConfig(changes, successKey, settingKey, successParams = {}) {
        const previousConfig = currentRuntimeConfig();
        const settingLabel = t(settingKey);
        runtimeState.runtimeConfigLoading = true;
        updateRuntimeControls();
        setRunStatus(t("console.runtime.updating", { setting: settingLabel }));

        try {
            const payload = await requestJson("/api/web/runtime", {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(changes),
            });
            if (appState.config) {
                appState.config.runtime = payload;
            }
            applyRuntimeConfig(payload);
            setRunStatus(t(successKey, successParams));
        } catch (error) {
            console.error(error);
            applyRuntimeConfig(previousConfig);
            addMessage(
                "system",
                t("console.runtime.updateFailed", {
                    setting: settingLabel,
                    error: error.message || error,
                }),
                t("console.systemLabel"),
                { labelKey: "console.systemLabel" },
            );
            setRunStatus(error.message || t("console.runtime.updateFailedShort", { setting: settingLabel }));
        } finally {
            runtimeState.runtimeConfigLoading = false;
            updateRuntimeControls();
        }
    }

    async function resetRuntimeConfig() {
        const previousConfig = currentRuntimeConfig();
        runtimeState.runtimeConfigLoading = true;
        updateRuntimeControls();
        setRunStatus(t("console.runtime.resetting"));

        try {
            const payload = await requestJson("/api/web/runtime/reset", {
                method: "POST",
            });
            if (appState.config) {
                appState.config.runtime = payload;
            }
            applyRuntimeConfig(payload);
            setRunStatus(t("console.runtime.resetCleared"));
        } catch (error) {
            console.error(error);
            applyRuntimeConfig(previousConfig);
            addMessage(
                "system",
                t("console.runtime.resetFailed", { error: error.message || error }),
                t("console.systemLabel"),
                { labelKey: "console.systemLabel" },
            );
            setRunStatus(error.message || t("console.runtime.resetFailedShort"));
        } finally {
            runtimeState.runtimeConfigLoading = false;
            updateRuntimeControls();
        }
    }

    function formatShellSafetyModeLabel(mode) {
        const labelKey = SHELL_SAFETY_MODE_LABEL_KEYS[mode];
        return labelKey ? t(labelKey) : mode;
    }

    function updateRuntimeControls() {
        if (DOM.delegatedAckCheckbox) {
            DOM.delegatedAckCheckbox.disabled = runtimeState.runtimeConfigLoading;
        }
        if (DOM.shellSafetyModeSelect) {
            DOM.shellSafetyModeSelect.disabled = runtimeState.runtimeConfigLoading;
        }
        if (DOM.fileWriteEnabledCheckbox) {
            DOM.fileWriteEnabledCheckbox.disabled = runtimeState.runtimeConfigLoading;
        }
        if (DOM.cronMutationEnabledCheckbox) {
            DOM.cronMutationEnabledCheckbox.disabled = runtimeState.runtimeConfigLoading;
        }
        if (DOM.webPrivateNetworkEnabledCheckbox) {
            DOM.webPrivateNetworkEnabledCheckbox.disabled = runtimeState.runtimeConfigLoading;
        }
        if (DOM.runtimeResetButton) {
            DOM.runtimeResetButton.disabled = runtimeState.runtimeConfigLoading;
        }
    }

    return {
        applyRuntimeConfig,
        handleCronMutationToggle,
        handleDelegatedAckToggle,
        handleFileWriteToggle,
        handleRuntimeReset,
        handleShellSafetyModeChange,
        handleWebPrivateNetworkToggle,
    };
}

import { DOM } from "../core/dom.js";

export function createRuntimeEditsController(deps = {}) {
    const t = typeof deps.t === "function" ? deps.t : (key) => key;
    let dirty = false;
    let initialized = false;

    function initialize() {
        if (initialized) {
            return;
        }
        initialized = true;
        window.addEventListener("beforeunload", handleBeforeUnload);
        render();
    }

    function markRuntimeDirty() {
        dirty = true;
        render();
    }

    function markApplied() {
        dirty = false;
        render();
    }

    function confirmDiscardChanges() {
        return !dirty || window.confirm(t("console.runtimeChangesDiscardConfirm"));
    }

    function handleBeforeUnload(event) {
        if (!dirty) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    }

    function render() {
        [DOM.sessionSettingsSaveButton, DOM.stageBackgroundApplyButton]
            .filter(Boolean)
            .forEach((button) => {
                button.classList.toggle("has-pending-runtime-changes", dirty);
                button.dataset.runtimeDirty = dirty ? "true" : "false";
            });

        if (DOM.sessionRuntimeChangeStatus) {
            const state = dirty ? "pending" : "applied";
            const key = dirty
                ? "console.runtimeChangesPending"
                : "console.runtimeAppliedToStage";
            DOM.sessionRuntimeChangeStatus.hidden = false;
            DOM.sessionRuntimeChangeStatus.dataset.runtimeState = state;
            DOM.sessionRuntimeChangeStatus.dataset.i18nKey = key;
            DOM.sessionRuntimeChangeStatus.classList.toggle("is-pending", dirty);
            DOM.sessionRuntimeChangeStatus.classList.toggle("is-applied", !dirty);
            DOM.sessionRuntimeChangeStatus.textContent = t(key);
        }
    }

    return {
        confirmDiscardChanges,
        initialize,
        isDirty: () => dirty,
        markApplied,
        markRuntimeDirty,
        refreshLocalizedText: render,
    };
}

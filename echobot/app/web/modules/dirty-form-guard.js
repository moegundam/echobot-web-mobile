export function createDirtyFormGuard({ form, elements = [], confirmDiscard } = {}) {
    if (!form) {
        throw new Error("A form element is required for dirty-state tracking.");
    }

    let dirty = false;

    const markDirty = () => {
        dirty = true;
        form.dataset.dirty = "true";
    };

    const clear = () => {
        dirty = false;
        delete form.dataset.dirty;
    };

    const confirmDiscardChanges = () => {
        if (!dirty) {
            return true;
        }
        if (typeof confirmDiscard === "function" && !confirmDiscard()) {
            return false;
        }
        clear();
        return true;
    };

    const handleBeforeUnload = (event) => {
        if (!dirty) {
            return;
        }
        event.preventDefault();
        event.returnValue = "";
    };

    [form, ...elements].forEach((element) => {
        if (!element) {
            return;
        }
        element.addEventListener("input", markDirty);
        element.addEventListener("change", markDirty);
    });
    window.addEventListener("beforeunload", handleBeforeUnload);

    return {
        markDirty,
        clear,
        confirmDiscard: confirmDiscardChanges,
        isDirty: () => dirty,
    };
}

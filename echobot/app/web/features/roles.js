import {
    DEFAULT_SESSION_NAME,
    chatState,
    roleState,
    sessionState,
} from "../core/store.js";
import { DOM } from "../core/dom.js";

export function createRolesModule(deps) {
    const {
        addMessage,
        normalizeSessionName,
        requestJson,
        setRunStatus,
        t = (key) => key,
    } = deps;

    let sessionHooks = {
        applySessionDetail() {},
    };

    function bindSessionHooks(hooks) {
        sessionHooks = {
            ...sessionHooks,
            ...(hooks || {}),
        };
    }

    async function initializeRolePanel() {
        await refreshRolePanel({ silent: true });
    }

    async function syncRolePanelForCurrentSession() {
        const roleSummaries = Array.isArray(roleState.roles) ? roleState.roles : [];
        const hasCurrentRole = roleSummaries.some(
            (item) => item && item.name === roleState.currentRoleName,
        );

        if (hasCurrentRole) {
            renderRoleSelectOptions();
        } else if (!roleState.roleLoading) {
            await refreshRoleList({ silent: true });
        }
        await refreshCurrentRoleCard({ silent: true });
    }

    async function refreshRolePanel(options = {}) {
        await refreshRoleList(options);
        await refreshCurrentRoleCard(options);
    }

    async function refreshRoleList(options = {}) {
        if (roleState.roleLoading) {
            return;
        }

        setRoleControlsBusy(true, options.silent ? null : t("console.roleLoading"));
        try {
            const payload = await requestJson("/api/roles");
            roleState.roles = Array.isArray(payload) ? payload : [];
            renderRoleSelectOptions();
            if (!options.silent) {
                setRoleStatus("");
            }
        } catch (error) {
            console.error(error);
            renderRoleSelectOptions();
            if (!options.silent) {
                setRoleStatus(error.message || t("console.roleLoadFailed"));
                addMessage("system", `${t("console.roleLoadFailed")}: ${error.message || error}`, t("console.systemLabel"));
            }
        } finally {
            setRoleControlsBusy(false);
        }
    }

    async function refreshCurrentRoleCard(options = {}) {
        const roleName = roleState.currentRoleName || "default";
        if (!roleName) {
            roleState.currentRoleCard = null;
            renderCurrentRoleCard();
            return;
        }

        try {
            roleState.currentRoleCard = await requestJson(
                `/api/roles/${encodeURIComponent(roleName)}`,
            );
        } catch (error) {
            console.error(error);
            roleState.currentRoleCard = null;
            if (!options.silent) {
                setRoleStatus(error.message || t("console.roleDetailLoadFailed"));
                addMessage("system", `${t("console.roleDetailLoadFailed")}: ${error.message || error}`, t("console.systemLabel"));
            }
        }

        renderCurrentRoleCard();
    }

    function renderRoleSelectOptions() {
        if (!DOM.roleSelect) {
            return;
        }

        DOM.roleSelect.innerHTML = "";
        const roleSummaries = Array.isArray(roleState.roles) ? roleState.roles : [];
        if (roleSummaries.length === 0) {
            const option = document.createElement("option");
            option.value = "default";
            option.textContent = t("console.defaultRoleOption");
            DOM.roleSelect.appendChild(option);
            DOM.roleSelect.disabled = true;
            return;
        }

        const availableNames = new Set(roleSummaries.map((item) => item.name));
        if (!availableNames.has(roleState.currentRoleName)) {
            roleState.currentRoleName = availableNames.has("default")
                ? "default"
                : roleSummaries[0].name;
        }

        roleSummaries.forEach((roleSummary) => {
            const option = document.createElement("option");
            option.value = roleSummary.name;
            option.textContent = buildRoleOptionLabel(roleSummary);
            DOM.roleSelect.appendChild(option);
        });
        DOM.roleSelect.value = roleState.currentRoleName;
        updateRoleActionState();
    }

    function buildRoleOptionLabel(roleSummary) {
        const name = String((roleSummary && roleSummary.name) || "default");
        if (name === "default") {
            return t("console.defaultRoleOption", { role: name });
        }
        return name;
    }

    function renderCurrentRoleCard() {
        const roleCard = roleState.currentRoleCard;

        if (DOM.rolePromptPreview) {
            DOM.rolePromptPreview.textContent = roleCard && roleCard.prompt
                ? roleCard.prompt
                : t("console.noRoleContent");
        }

        if (DOM.roleStatus) {
            if (!roleCard) {
                DOM.roleStatus.textContent = t("console.noRoleDetail");
            } else if (!roleCard.editable) {
                DOM.roleStatus.textContent = t("console.currentRoleReadonly", { role: roleCard.name });
            } else {
                DOM.roleStatus.textContent = t("console.currentRoleStatus", { role: roleCard.name });
            }
        }

        updateRoleActionState();
    }

    function setRoleControlsBusy(isBusy, statusText = null) {
        roleState.roleLoading = isBusy;
        if (typeof statusText === "string") {
            setRoleStatus(statusText);
        }
        updateRoleActionState();
    }

    function setRoleStatus(text) {
        if (!DOM.roleStatus) {
            return;
        }
        DOM.roleStatus.textContent = String(text || "").trim();
    }

    function updateRoleActionState() {
        const roleCard = roleState.currentRoleCard;
        const isBusy = chatState.chatBusy || roleState.roleLoading;
        const editorOpen = roleState.roleEditorMode !== "closed";
        const controlsLocked = isBusy || editorOpen;

        if (DOM.roleSelect) {
            DOM.roleSelect.disabled = controlsLocked || !roleState.roles || roleState.roles.length === 0;
        }
        if (DOM.roleRefreshButton) {
            DOM.roleRefreshButton.disabled = controlsLocked;
        }
        if (DOM.roleNewButton) {
            DOM.roleNewButton.disabled = controlsLocked;
        }
        if (DOM.roleEditButton) {
            DOM.roleEditButton.disabled = controlsLocked || !roleCard || !roleCard.editable;
        }
        if (DOM.roleDeleteButton) {
            DOM.roleDeleteButton.disabled = controlsLocked || !roleCard || !roleCard.deletable;
        }
        if (DOM.roleSaveButton) {
            DOM.roleSaveButton.disabled = isBusy || !editorOpen;
        }
        if (DOM.roleCancelButton) {
            DOM.roleCancelButton.disabled = roleState.roleLoading;
        }
        if (DOM.rolePreview) {
            DOM.rolePreview.hidden = editorOpen;
        }
        if (DOM.roleEditor) {
            DOM.roleEditor.hidden = !editorOpen;
        }
        if (DOM.roleNameInput) {
            DOM.roleNameInput.disabled = roleState.roleLoading || roleState.roleEditorMode !== "create";
            DOM.roleNameInput.readOnly = roleState.roleEditorMode !== "create";
        }
        if (DOM.rolePromptInput) {
            DOM.rolePromptInput.disabled = roleState.roleLoading || !editorOpen;
        }
    }

    async function handleRoleSelectionChange() {
        if (!DOM.roleSelect) {
            return;
        }

        const nextRoleName = String(DOM.roleSelect.value || "").trim();
        if (
            !nextRoleName
            || nextRoleName === roleState.currentRoleName
            || chatState.chatBusy
            || roleState.roleLoading
        ) {
            renderRoleSelectOptions();
            return;
        }

        closeRoleEditor();
        setRoleControlsBusy(true, t("console.switchingRole"));
        try {
            await setCurrentSessionRole(nextRoleName, { silent: true });
            await refreshCurrentRoleCard({ silent: true });
            setRunStatus(t("console.roleSwitched", { role: roleState.currentRoleName }));
            setRoleStatus("");
        } catch (error) {
            console.error(error);
            renderRoleSelectOptions();
            setRoleStatus(error.message || t("console.roleSwitchFailed"));
            addMessage("system", `${t("console.roleSwitchFailed")}: ${error.message || error}`, t("console.systemLabel"));
        } finally {
            setRoleControlsBusy(false);
        }
    }

    async function setCurrentSessionRole(roleName, options = {}) {
        const sessionName = normalizeSessionName(
            sessionState.currentSessionName || DEFAULT_SESSION_NAME,
        );
        const sessionDetail = await requestJson(
            `/api/sessions/${encodeURIComponent(sessionName)}/role`,
            {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ role_name: roleName }),
            },
        );
        sessionHooks.applySessionDetail(sessionDetail);
        if (!options.silent) {
            setRunStatus(t("console.roleSwitched", { role: sessionDetail.role_name || roleName }));
        }
        return sessionDetail;
    }

    function openRoleEditor(mode) {
        if (!DOM.roleEditor || !DOM.roleNameInput || !DOM.rolePromptInput || !DOM.roleEditorTitle) {
            return;
        }

        if (mode === "edit" && (!roleState.currentRoleCard || !roleState.currentRoleCard.editable)) {
            return;
        }

        roleState.roleEditorMode = mode;
        DOM.roleEditor.hidden = false;
        if (mode === "create") {
            DOM.roleEditorTitle.textContent = t("console.newRoleCard");
            DOM.roleNameInput.value = "";
            DOM.rolePromptInput.value = "";
            DOM.roleNameInput.focus();
        } else {
            DOM.roleEditorTitle.textContent = t("console.editRoleCard", { role: roleState.currentRoleCard.name });
            DOM.roleNameInput.value = roleState.currentRoleCard.name || "";
            DOM.rolePromptInput.value = roleState.currentRoleCard.prompt || "";
            DOM.rolePromptInput.focus();
        }
        updateRoleActionState();
    }

    function closeRoleEditor() {
        roleState.roleEditorMode = "closed";
        if (DOM.roleEditor) {
            DOM.roleEditor.hidden = true;
        }
        if (DOM.roleNameInput) {
            DOM.roleNameInput.value = "";
        }
        if (DOM.rolePromptInput) {
            DOM.rolePromptInput.value = "";
        }
        if (DOM.roleEditorTitle) {
            DOM.roleEditorTitle.textContent = t("console.roleEditor");
        }
        updateRoleActionState();
    }

    async function handleEditRoleClick() {
        if (!roleState.currentRoleCard || !roleState.currentRoleCard.editable) {
            return;
        }
        await refreshCurrentRoleCard({ silent: true });
        openRoleEditor("edit");
    }

    async function handleSaveRoleClick() {
        if (
            chatState.chatBusy
            || roleState.roleLoading
            || roleState.roleEditorMode === "closed"
        ) {
            return;
        }

        const roleName = DOM.roleNameInput ? DOM.roleNameInput.value.trim() : "";
        const prompt = DOM.rolePromptInput ? DOM.rolePromptInput.value.trim() : "";
        const isCreateMode = roleState.roleEditorMode === "create";
        let shouldRefreshRoleList = false;
        if (!prompt) {
            setRoleStatus(t("console.rolePromptRequired"));
            return;
        }
        if (isCreateMode && !roleName) {
            setRoleStatus(t("console.roleNameRequired"));
            return;
        }

        setRoleControlsBusy(
            true,
            isCreateMode ? t("console.creatingRole") : t("console.savingRole"),
        );
        try {
            let roleDetail;
            if (isCreateMode) {
                roleDetail = await requestJson("/api/roles", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        name: roleName,
                        prompt: prompt,
                    }),
                });
                await setCurrentSessionRole(roleDetail.name, { silent: true });
                shouldRefreshRoleList = true;
            } else {
                roleDetail = await requestJson(
                    `/api/roles/${encodeURIComponent(roleState.currentRoleName)}`,
                    {
                        method: "PUT",
                        headers: {
                            "Content-Type": "application/json",
                        },
                        body: JSON.stringify({
                            prompt: prompt,
                        }),
                    },
                );
            }

            roleState.currentRoleName = roleDetail.name || roleState.currentRoleName;
            roleState.currentRoleCard = roleDetail;
            renderCurrentRoleCard();
            closeRoleEditor();
            await refreshCurrentRoleCard({ silent: true });
            setRoleStatus("");
            setRunStatus(
                isCreateMode
                    ? t("console.roleCreated", { role: roleDetail.name })
                    : t("console.roleSaved", { role: roleDetail.name }),
            );
        } catch (error) {
            console.error(error);
            setRoleStatus(error.message || t("console.saveRoleFailed"));
            addMessage("system", `${t("console.saveRoleFailed")}: ${error.message || error}`, t("console.systemLabel"));
        } finally {
            setRoleControlsBusy(false);
        }

        if (shouldRefreshRoleList) {
            await refreshRoleList({ silent: true });
        }
    }

    async function handleDeleteRoleClick() {
        const roleCard = roleState.currentRoleCard;
        if (
            !roleCard
            || !roleCard.deletable
            || chatState.chatBusy
            || roleState.roleLoading
        ) {
            return;
        }
        if (!window.confirm(t("console.deleteRoleConfirm", { role: roleCard.name }))) {
            return;
        }

        let shouldRefreshRoleList = false;
        setRoleControlsBusy(true, t("console.deletingRole"));
        try {
            await requestJson(`/api/roles/${encodeURIComponent(roleCard.name)}`, {
                method: "DELETE",
            });
            shouldRefreshRoleList = true;
            closeRoleEditor();
            const sessionDetail = await requestJson("/api/sessions/current");
            sessionHooks.applySessionDetail(sessionDetail);
            await refreshCurrentRoleCard({ silent: true });
            setRoleStatus("");
            setRunStatus(t("console.roleDeleted", { role: roleCard.name }));
        } catch (error) {
            console.error(error);
            setRoleStatus(error.message || t("console.deleteRoleFailed"));
            addMessage("system", `${t("console.deleteRoleFailed")}: ${error.message || error}`, t("console.systemLabel"));
        } finally {
            setRoleControlsBusy(false);
        }

        if (shouldRefreshRoleList) {
            await refreshRoleList({ silent: true });
        }
    }

    return {
        bindSessionHooks: bindSessionHooks,
        initializeRolePanel: initializeRolePanel,
        syncRolePanelForCurrentSession: syncRolePanelForCurrentSession,
        refreshRolePanel: refreshRolePanel,
        handleRoleSelectionChange: handleRoleSelectionChange,
        handleEditRoleClick: handleEditRoleClick,
        handleSaveRoleClick: handleSaveRoleClick,
        handleDeleteRoleClick: handleDeleteRoleClick,
        openRoleEditor: openRoleEditor,
        closeRoleEditor: closeRoleEditor,
        updateRoleActionState: updateRoleActionState,
        refreshLocalizedText() {
            renderRoleSelectOptions();
            renderCurrentRoleCard();
            if (roleState.roleEditorMode === "create" && DOM.roleEditorTitle) {
                DOM.roleEditorTitle.textContent = t("console.newRoleCard");
            } else if (roleState.roleEditorMode === "edit" && DOM.roleEditorTitle && roleState.currentRoleCard) {
                DOM.roleEditorTitle.textContent = t("console.editRoleCard", { role: roleState.currentRoleCard.name });
            }
        },
    };
}

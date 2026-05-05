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
        getModelProfilesPayload = () => null,
        normalizeSessionName,
        requestJson,
        setRunStatus,
        syncModelProfileFromServer = async () => null,
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

    function renderRoleModelProfileCard() {
        if (!DOM.roleModelProfileLink || !DOM.roleModelProfileDetail) {
            return;
        }

        const roleName = roleState.currentRoleName || "default";
        const profilePayload = getModelProfilesPayload() || {};
        const roleBindings = profilePayload.role_bindings || {};
        const boundProfileId = String(roleBindings[roleName] || "").trim();
        const boundProfile = findModelProfileById(boundProfileId);

        DOM.roleModelProfileLink.href = "/admin/models";
        if (boundProfile) {
            DOM.roleModelProfileLink.textContent = modelProfileLabel(boundProfile);
            DOM.roleModelProfileDetail.textContent = t(
                "console.roleModelProfileBound",
                { profile: modelProfileLabel(boundProfile) },
            );
            return;
        }

        DOM.roleModelProfileLink.textContent = t("models.useActiveProfile");
        DOM.roleModelProfileDetail.textContent = boundProfileId
            ? t("console.roleModelProfileMissing", { profile: boundProfileId.toUpperCase() })
            : t("console.roleModelProfileUnbound");
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

        renderRoleModelProfileCard();
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
        const isBusy = chatState.chatBusy || roleState.roleLoading;

        if (DOM.roleSelect) {
            DOM.roleSelect.disabled = isBusy || !roleState.roles || roleState.roles.length === 0;
        }
        if (DOM.roleRefreshButton) {
            DOM.roleRefreshButton.disabled = isBusy;
        }
        if (DOM.rolePreview) {
            DOM.rolePreview.hidden = false;
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

        setRoleControlsBusy(true, t("console.switchingRole"));
        try {
            const expectedBoundProfile = modelProfileForRole(nextRoleName);
            await setCurrentSessionRole(nextRoleName, { silent: true });
            if (expectedBoundProfile) {
                await syncModelProfileFromServer();
            }
            await refreshCurrentRoleCard({ silent: true });
            const boundProfile = modelProfileForRole(roleState.currentRoleName);
            if (boundProfile) {
                setRunStatus(t("console.roleSwitchedWithProfile", {
                    role: roleState.currentRoleName,
                    profile: modelProfileLabel(boundProfile),
                }));
            } else {
                setRunStatus(t("console.roleSwitched", { role: roleState.currentRoleName }));
            }
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

    function findModelProfileById(profileId) {
        const payload = getModelProfilesPayload() || {};
        const profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
        return profiles.find((profile) => profile && profile.profile_id === profileId) || null;
    }

    function modelProfileForRole(roleName) {
        const payload = getModelProfilesPayload() || {};
        const bindings = payload.role_bindings || {};
        const profileId = String(bindings[String(roleName || "").trim()] || "").trim();
        return findModelProfileById(profileId);
    }

    function modelProfileLabel(profile) {
        if (!profile) {
            return "";
        }
        const profileId = String(profile.profile_id || "").trim();
        const code = profileId ? profileId.toUpperCase() : "";
        const label = String(profile.label || code || t("models.defaultProfile")).trim();
        return code ? `${code} · ${label}` : label;
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

    return {
        bindSessionHooks: bindSessionHooks,
        initializeRolePanel: initializeRolePanel,
        syncRolePanelForCurrentSession: syncRolePanelForCurrentSession,
        refreshRolePanel: refreshRolePanel,
        handleRoleSelectionChange: handleRoleSelectionChange,
        updateRoleActionState: updateRoleActionState,
        refreshLocalizedText() {
            renderRoleSelectOptions();
            renderCurrentRoleCard();
            renderRoleModelProfileCard();
        },
    };
}

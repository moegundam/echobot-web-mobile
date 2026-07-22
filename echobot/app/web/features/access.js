import { DOM } from "../core/dom.js";
import { sessionState } from "../core/store.js";

const ACCESS_ROLE_LABEL_KEYS = {
    admin: "console.accessRoleAdmin",
    operator: "console.accessRoleOperator",
    user: "console.accessRoleUser",
};

export function applyAccessContext(config, t = (key) => key) {
    const access = config && config.access && typeof config.access === "object"
        ? config.access
        : {};
    const role = String(access.role || "user").trim().toLowerCase();
    const canAccessConsole = access.can_access_console === true;
    const canManageAdmin = access.can_manage_admin === true;
    const canUseAgent = access.can_use_agent === true;

    document.querySelectorAll("[data-admin-only]").forEach((element) => {
        element.hidden = !canManageAdmin;
    });
    document.querySelectorAll("[data-operator-only]").forEach((element) => {
        element.hidden = !canAccessConsole;
    });
    document.querySelectorAll("[data-agent-route]").forEach((element) => {
        element.hidden = !canUseAgent;
        element.disabled = !canUseAgent;
    });

    if (!canManageAdmin) {
        removePersistentLive2DEditCapability(config);
    }
    if (!canUseAgent && DOM.routeModeSelect) {
        DOM.routeModeSelect.value = "chat_only";
        sessionState.currentRouteMode = "chat_only";
    }

    if (DOM.accessRoleBadge) {
        DOM.accessRoleBadge.hidden = false;
        DOM.accessRoleBadge.dataset.accessRole = role;
        DOM.accessRoleBadge.textContent = t(
            ACCESS_ROLE_LABEL_KEYS[role] || ACCESS_ROLE_LABEL_KEYS.user,
        );
    }

    return {
        role,
        can_access_console: canAccessConsole,
        can_manage_admin: canManageAdmin,
        can_use_agent: canUseAgent,
    };
}

function removePersistentLive2DEditCapability(config) {
    const live2d = config && config.live2d && typeof config.live2d === "object"
        ? config.live2d
        : null;
    if (!live2d) {
        return;
    }
    live2d.annotations_writable = false;
    if (Array.isArray(live2d.models)) {
        live2d.models.forEach((model) => {
            if (model && typeof model === "object") {
                model.annotations_writable = false;
            }
        });
    }
}

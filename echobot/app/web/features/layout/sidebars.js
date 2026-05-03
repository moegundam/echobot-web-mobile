import { DOM } from "../../core/dom.js";
import { panelState } from "../../core/store.js";
import { readBoolean, writeBoolean } from "../../core/storage.js";

const SESSION_SIDEBAR_STORAGE_KEY = "echobot.web.session_sidebar_open";
const ROLE_SIDEBAR_STORAGE_KEY = "echobot.web.role_sidebar_open";
const LIVE2D_DRAWER_TABS = ["expression", "motion", "hotkey"];

export function createSidebarController({ t } = {}) {
    const translate = typeof t === "function" ? t : (key) => key;

    function ensureSidebarToggleButtons() {
        const sessionToggle = DOM.sessionSidebarToggle;
        if (!sessionToggle) {
            return;
        }

        let actions = sessionToggle.parentElement;
        if (!actions || !actions.classList.contains("panel-header-actions")) {
            actions = document.createElement("div");
            actions.className = "panel-header-actions";
            sessionToggle.insertAdjacentElement("afterend", actions);
            actions.appendChild(sessionToggle);
        }

        let roleToggle = DOM.roleSidebarToggle || document.getElementById("role-sidebar-toggle");
        if (!roleToggle) {
            roleToggle = document.createElement("button");
            roleToggle.id = "role-sidebar-toggle";
            roleToggle.type = "button";
            roleToggle.className = "ghost-button ghost-button-compact";
            actions.appendChild(roleToggle);
        }

        DOM.roleSidebarToggle = roleToggle;
        updateSidebarToggleLabels();
    }

    function stopSummaryButtonToggle(event) {
        if (!event) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
    }

    function restoreSessionSidebarState() {
        setSessionSidebarOpen(readBoolean(SESSION_SIDEBAR_STORAGE_KEY, false));
    }

    function restoreRoleSidebarState() {
        setRoleSidebarOpen(readBoolean(ROLE_SIDEBAR_STORAGE_KEY, false));
    }

    function initializeLive2DDrawer() {
        setLive2DDrawerTab(panelState.live2dDrawerTab, { openDrawer: false });
        setLive2DDrawerOpen(false);
    }

    function setSessionSidebarOpen(isOpen, options = {}) {
        panelState.sessionSidebarOpen = Boolean(isOpen);
        if (
            panelState.sessionSidebarOpen
            && options.closeOther !== false
            && panelState.roleSidebarOpen
        ) {
            setRoleSidebarOpen(false, { closeOther: false });
        }

        if (DOM.chatPanel) {
            DOM.chatPanel.classList.toggle("sessions-open", panelState.sessionSidebarOpen);
        }
        if (DOM.sessionSidebar) {
            DOM.sessionSidebar.setAttribute("aria-hidden", String(!panelState.sessionSidebarOpen));
        }
        if (DOM.sessionSidebarBackdrop) {
            DOM.sessionSidebarBackdrop.hidden = !panelState.sessionSidebarOpen;
        }
        if (DOM.sessionSidebarToggle) {
            DOM.sessionSidebarToggle.setAttribute("aria-expanded", String(panelState.sessionSidebarOpen));
        }

        updateSidebarToggleLabels();
        writeBoolean(SESSION_SIDEBAR_STORAGE_KEY, panelState.sessionSidebarOpen);
    }

    function setRoleSidebarOpen(isOpen, options = {}) {
        panelState.roleSidebarOpen = Boolean(isOpen);
        if (
            panelState.roleSidebarOpen
            && options.closeOther !== false
            && panelState.sessionSidebarOpen
        ) {
            setSessionSidebarOpen(false, { closeOther: false });
        }

        if (DOM.chatPanel) {
            DOM.chatPanel.classList.toggle("roles-open", panelState.roleSidebarOpen);
        }
        if (DOM.roleSidebar) {
            DOM.roleSidebar.setAttribute("aria-hidden", String(!panelState.roleSidebarOpen));
        }
        if (DOM.roleSidebarBackdrop) {
            DOM.roleSidebarBackdrop.hidden = !panelState.roleSidebarOpen;
        }
        if (DOM.roleSidebarToggle) {
            DOM.roleSidebarToggle.setAttribute("aria-expanded", String(panelState.roleSidebarOpen));
        }

        updateSidebarToggleLabels();
        writeBoolean(ROLE_SIDEBAR_STORAGE_KEY, panelState.roleSidebarOpen);
    }

    function updateSidebarToggleLabels() {
        if (DOM.sessionSidebarToggle) {
            DOM.sessionSidebarToggle.textContent = panelState.sessionSidebarOpen
                ? translate("console.hideSession")
                : translate("console.sessionList");
        }
        if (DOM.roleSidebarToggle) {
            DOM.roleSidebarToggle.textContent = panelState.roleSidebarOpen
                ? translate("console.hideRoleCard")
                : translate("console.roleCard");
        }
    }

    function setLive2DDrawerOpen(isOpen) {
        panelState.live2dDrawerOpen = Boolean(isOpen);

        document.body.classList.toggle("live2d-drawer-open", panelState.live2dDrawerOpen);
        if (DOM.live2dDrawer) {
            DOM.live2dDrawer.setAttribute("aria-hidden", String(!panelState.live2dDrawerOpen));
        }
        if (DOM.live2dDrawerBackdrop) {
            DOM.live2dDrawerBackdrop.hidden = !panelState.live2dDrawerOpen;
        }
        if (DOM.live2dDrawerToggle) {
            DOM.live2dDrawerToggle.setAttribute("aria-expanded", String(panelState.live2dDrawerOpen));
        }
    }

    function setLive2DDrawerTab(tabKey, options = {}) {
        const normalizedTab = LIVE2D_DRAWER_TABS.includes(tabKey) ? tabKey : "expression";
        panelState.live2dDrawerTab = normalizedTab;

        const tabEntries = [
            ["expression", DOM.live2dExpressionPanel, DOM.live2dTabExpression],
            ["motion", DOM.live2dMotionPanel, DOM.live2dTabMotion],
            ["hotkey", DOM.live2dHotkeyPanel, DOM.live2dTabHotkey],
        ];
        tabEntries.forEach(([entryKey, panel, button]) => {
            const isActive = entryKey === panelState.live2dDrawerTab;
            if (panel) {
                panel.hidden = !isActive;
            }
            if (button) {
                button.classList.toggle("is-active", isActive);
                button.setAttribute("aria-selected", String(isActive));
                button.tabIndex = isActive ? 0 : -1;
            }
        });

        if (options.openDrawer !== false) {
            setLive2DDrawerOpen(true);
        }
    }

    return {
        ensureSidebarToggleButtons,
        initializeLive2DDrawer,
        refreshSidebarLabels: updateSidebarToggleLabels,
        restoreRoleSidebarState,
        restoreSessionSidebarState,
        setLive2DDrawerOpen,
        setLive2DDrawerTab,
        setRoleSidebarOpen,
        setSessionSidebarOpen,
        stopSummaryButtonToggle,
    };
}

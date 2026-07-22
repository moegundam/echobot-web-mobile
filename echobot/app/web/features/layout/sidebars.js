import { DOM } from "../../core/dom.js";
import { panelState } from "../../core/store.js";
import { readBoolean, writeBoolean } from "../../core/storage.js";

const SESSION_SIDEBAR_STORAGE_KEY = "echobot.web.session_sidebar_open";
const ROLE_SIDEBAR_STORAGE_KEY = "echobot.web.role_sidebar_open";
const LIVE2D_DRAWER_TABS = ["expression", "motion", "hotkey"];
const DRAWER_FOCUSABLE_SELECTOR = [
    "a[href]",
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex='-1'])",
].join(", ");

export function createSidebarController({ t } = {}) {
    const translate = typeof t === "function" ? t : (key) => key;
    const drawerPreviousFocus = new Map();
    const drawerOpenOrder = [];

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
        setSessionSidebarOpen(readBoolean(SESSION_SIDEBAR_STORAGE_KEY, false), {
            manageFocus: false,
        });
    }

    function restoreRoleSidebarState() {
        setRoleSidebarOpen(readBoolean(ROLE_SIDEBAR_STORAGE_KEY, false), {
            manageFocus: false,
        });
    }

    function initializeLive2DDrawer() {
        setLive2DDrawerTab(panelState.live2dDrawerTab, { openDrawer: false });
        setLive2DDrawerOpen(false);
    }

    function setSessionSidebarOpen(isOpen, options = {}) {
        const wasOpen = panelState.sessionSidebarOpen;
        panelState.sessionSidebarOpen = Boolean(isOpen);
        if (
            panelState.sessionSidebarOpen
            && options.closeOther !== false
            && panelState.roleSidebarOpen
        ) {
            setRoleSidebarOpen(false, { closeOther: false, restoreFocus: false });
        }

        if (DOM.chatPanel) {
            DOM.chatPanel.classList.toggle("sessions-open", panelState.sessionSidebarOpen);
        }
        if (DOM.sessionSidebar) {
            syncDrawerAccessibility(
                DOM.sessionSidebar,
                panelState.sessionSidebarOpen,
                translate("console.sessionList"),
            );
        }
        if (DOM.sessionSidebarBackdrop) {
            DOM.sessionSidebarBackdrop.hidden = !panelState.sessionSidebarOpen;
        }
        if (DOM.sessionSidebarToggle) {
            DOM.sessionSidebarToggle.setAttribute("aria-expanded", String(panelState.sessionSidebarOpen));
        }

        syncDrawerFocusState({
            drawerKey: "session",
            drawer: DOM.sessionSidebar,
            fallbackToggle: DOM.sessionSidebarToggle,
            isOpen: panelState.sessionSidebarOpen,
            options,
            preferredFocus: DOM.sessionSidebarClose,
            wasOpen,
        });
        updateSidebarToggleLabels();
        writeBoolean(SESSION_SIDEBAR_STORAGE_KEY, panelState.sessionSidebarOpen);
    }

    function setRoleSidebarOpen(isOpen, options = {}) {
        const wasOpen = panelState.roleSidebarOpen;
        panelState.roleSidebarOpen = Boolean(isOpen);
        if (
            panelState.roleSidebarOpen
            && options.closeOther !== false
            && panelState.sessionSidebarOpen
        ) {
            setSessionSidebarOpen(false, { closeOther: false, restoreFocus: false });
        }

        if (DOM.chatPanel) {
            DOM.chatPanel.classList.toggle("roles-open", panelState.roleSidebarOpen);
        }
        if (DOM.roleSidebar) {
            syncDrawerAccessibility(
                DOM.roleSidebar,
                panelState.roleSidebarOpen,
                translate("console.roleCard"),
            );
        }
        if (DOM.roleSidebarBackdrop) {
            DOM.roleSidebarBackdrop.hidden = !panelState.roleSidebarOpen;
        }
        if (DOM.roleSidebarToggle) {
            DOM.roleSidebarToggle.setAttribute("aria-expanded", String(panelState.roleSidebarOpen));
        }

        syncDrawerFocusState({
            drawerKey: "role",
            drawer: DOM.roleSidebar,
            fallbackToggle: DOM.roleSidebarToggle,
            isOpen: panelState.roleSidebarOpen,
            options,
            preferredFocus: DOM.roleSidebarClose,
            wasOpen,
        });
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
        if (DOM.sessionSidebar) {
            DOM.sessionSidebar.setAttribute("aria-label", translate("console.sessionList"));
        }
        if (DOM.roleSidebar) {
            DOM.roleSidebar.setAttribute("aria-label", translate("console.roleCard"));
        }
        if (DOM.live2dDrawer) {
            DOM.live2dDrawer.setAttribute("aria-label", translate("console.live2dOptions"));
        }
    }

    function setLive2DDrawerOpen(isOpen, options = {}) {
        const wasOpen = panelState.live2dDrawerOpen;
        panelState.live2dDrawerOpen = Boolean(isOpen);

        document.body.classList.toggle("live2d-drawer-open", panelState.live2dDrawerOpen);
        if (DOM.live2dDrawer) {
            syncDrawerAccessibility(
                DOM.live2dDrawer,
                panelState.live2dDrawerOpen,
                translate("console.live2dOptions"),
            );
        }
        if (DOM.live2dDrawerBackdrop) {
            DOM.live2dDrawerBackdrop.hidden = !panelState.live2dDrawerOpen;
        }
        if (DOM.live2dDrawerToggle) {
            DOM.live2dDrawerToggle.setAttribute("aria-expanded", String(panelState.live2dDrawerOpen));
        }

        syncDrawerFocusState({
            drawerKey: "live2d",
            drawer: DOM.live2dDrawer,
            fallbackToggle: DOM.live2dDrawerToggle,
            isOpen: panelState.live2dDrawerOpen,
            options,
            preferredFocus: DOM.live2dDrawerClose,
            wasOpen,
        });
    }

    function setLive2DDrawerTab(tabKey, options = {}) {
        const normalizedTab = LIVE2D_DRAWER_TABS.includes(tabKey) ? tabKey : "expression";
        panelState.live2dDrawerTab = normalizedTab;

        const tabEntries = live2dTabEntries();
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
        if (options.focusTab) {
            const activeEntry = tabEntries.find(([entryKey]) => (
                entryKey === panelState.live2dDrawerTab
            ));
            const button = activeEntry?.[2];
            button?.focus({ preventScroll: true });
        }
    }

    function handleLive2DDrawerTabKeyDown(event) {
        const tabEntries = live2dTabEntries();
        const currentIndex = tabEntries.findIndex(([, , button]) => (
            button === event.currentTarget
        ));
        if (currentIndex < 0) {
            return;
        }

        let nextIndex = currentIndex;
        if (event.key === "ArrowRight") {
            nextIndex = (currentIndex + 1) % tabEntries.length;
        } else if (event.key === "ArrowLeft") {
            nextIndex = (currentIndex - 1 + tabEntries.length) % tabEntries.length;
        } else if (event.key === "Home") {
            nextIndex = 0;
        } else if (event.key === "End") {
            nextIndex = tabEntries.length - 1;
        } else {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        const nextTabKey = tabEntries[nextIndex][0];
        setLive2DDrawerTab(nextTabKey, { focusTab: true });
    }

    function handleDrawerKeyDown(event) {
        const activeDrawer = getActiveOpenDrawer();
        if (!activeDrawer) {
            return;
        }

        if (event.key === "Escape") {
            event.preventDefault();
            event.stopImmediatePropagation();
            activeDrawer.close();
            return;
        }
        if (event.key === "Tab") {
            event.stopImmediatePropagation();
            trapDrawerFocus(event, activeDrawer.element);
        }
    }

    function live2dTabEntries() {
        return [
            ["expression", DOM.live2dExpressionPanel, DOM.live2dTabExpression],
            ["motion", DOM.live2dMotionPanel, DOM.live2dTabMotion],
            ["hotkey", DOM.live2dHotkeyPanel, DOM.live2dTabHotkey],
        ];
    }

    function syncDrawerAccessibility(drawer, isOpen, label) {
        if (!drawer) {
            return;
        }
        drawer.setAttribute("role", "dialog");
        drawer.setAttribute("aria-modal", String(isOpen));
        drawer.setAttribute("aria-hidden", String(!isOpen));
        drawer.setAttribute("aria-label", label);
        drawer.toggleAttribute("inert", !isOpen);
        if (!drawer.hasAttribute("tabindex")) {
            drawer.tabIndex = -1;
        }
    }

    function syncDrawerFocusState({
        drawerKey,
        drawer,
        fallbackToggle,
        isOpen,
        options,
        preferredFocus,
        wasOpen,
    }) {
        if (isOpen) {
            markDrawerActive(drawerKey);
            if (!wasOpen && options.manageFocus !== false) {
                drawerPreviousFocus.set(drawerKey, document.activeElement);
                scheduleDrawerFocus(drawer, preferredFocus);
            }
            return;
        }

        removeDrawerFromOpenOrder(drawerKey);
        if (!wasOpen) {
            return;
        }
        if (options.restoreFocus === false) {
            drawerPreviousFocus.delete(drawerKey);
            return;
        }
        restoreDrawerFocus(drawerKey, fallbackToggle);
    }

    function markDrawerActive(drawerKey) {
        removeDrawerFromOpenOrder(drawerKey);
        drawerOpenOrder.push(drawerKey);
    }

    function removeDrawerFromOpenOrder(drawerKey) {
        const drawerIndex = drawerOpenOrder.indexOf(drawerKey);
        if (drawerIndex >= 0) {
            drawerOpenOrder.splice(drawerIndex, 1);
        }
    }

    function focusDrawer(drawer, preferredFocus) {
        if (!drawer) {
            return;
        }
        const firstFocusable = getDrawerFocusableElements(drawer)[0];
        const target = isUsableFocusTarget(preferredFocus)
            ? preferredFocus
            : firstFocusable || drawer;
        focusElement(target);
    }

    function scheduleDrawerFocus(drawer, preferredFocus) {
        window.setTimeout(() => {
            if (
                !drawer
                || drawer.hasAttribute("inert")
                || drawer.getAttribute("aria-hidden") !== "false"
            ) {
                return;
            }
            focusDrawer(drawer, preferredFocus);
        }, 0);
    }

    function restoreDrawerFocus(drawerKey, fallbackToggle) {
        const previousFocus = drawerPreviousFocus.get(drawerKey);
        drawerPreviousFocus.delete(drawerKey);
        const target = isUsableFocusTarget(previousFocus)
            ? previousFocus
            : fallbackToggle;
        focusElement(target);
    }

    function focusElement(element) {
        if (isUsableFocusTarget(element)) {
            element.focus({ preventScroll: true });
        }
    }

    function isUsableFocusTarget(element) {
        return Boolean(
            element
            && element.isConnected
            && element !== document.body
            && element !== document.documentElement
            && !element.inert
            && !element.closest?.("[inert], [hidden], [aria-hidden='true']")
            && typeof element.focus === "function"
        );
    }

    function getDrawerFocusableElements(drawer) {
        return Array.from(drawer.querySelectorAll(DRAWER_FOCUSABLE_SELECTOR)).filter((element) => (
            isUsableFocusTarget(element)
            && !element.closest("[hidden], [aria-hidden='true']")
        ));
    }

    function trapDrawerFocus(event, drawer) {
        const focusableElements = getDrawerFocusableElements(drawer);
        if (!focusableElements.length) {
            event.preventDefault();
            focusElement(drawer);
            return;
        }

        const first = focusableElements[0];
        const last = focusableElements[focusableElements.length - 1];
        const activeElement = document.activeElement;
        if (!drawer.contains(activeElement)) {
            event.preventDefault();
            focusElement(first);
        } else if (event.shiftKey && activeElement === first) {
            event.preventDefault();
            focusElement(last);
        } else if (!event.shiftKey && activeElement === last) {
            event.preventDefault();
            focusElement(first);
        }
    }

    function getActiveOpenDrawer() {
        for (let index = drawerOpenOrder.length - 1; index >= 0; index -= 1) {
            const descriptor = drawerDescriptor(drawerOpenOrder[index]);
            if (descriptor?.isOpen && descriptor.element) {
                return descriptor;
            }
        }
        return null;
    }

    function drawerDescriptor(drawerKey) {
        if (drawerKey === "live2d") {
            return {
                close: () => setLive2DDrawerOpen(false),
                element: DOM.live2dDrawer,
                isOpen: panelState.live2dDrawerOpen,
            };
        }
        if (drawerKey === "role") {
            return {
                close: () => setRoleSidebarOpen(false),
                element: DOM.roleSidebar,
                isOpen: panelState.roleSidebarOpen,
            };
        }
        if (drawerKey === "session") {
            return {
                close: () => setSessionSidebarOpen(false),
                element: DOM.sessionSidebar,
                isOpen: panelState.sessionSidebarOpen,
            };
        }
        return null;
    }

    return {
        ensureSidebarToggleButtons,
        handleDrawerKeyDown,
        handleLive2DDrawerTabKeyDown,
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

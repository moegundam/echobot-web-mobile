import { DOM } from "../../core/dom.js";
import { panelState } from "../../core/store.js";

const WORKSPACE_VIEWS = ["stage", "operations", "chat"];

export function initMobileConsoleWorkspace({ onViewChange = () => {} } = {}) {
    const root = document.documentElement;
    const tabs = workspaceTabs();
    const regions = workspaceRegions();

    if (!DOM.pageShell || !DOM.consoleMobileWorkspaceTabs || tabs.length !== WORKSPACE_VIEWS.length) {
        return createNoopController();
    }

    tabs.forEach(({ button, view }) => {
        button.addEventListener("click", () => setView(view));
        button.addEventListener("keydown", (event) => handleTabKeydown(event, view));
    });

    const layoutObserver = new MutationObserver(syncLayoutMode);
    layoutObserver.observe(root, {
        attributes: true,
        attributeFilter: ["data-layout-mode", "data-viewport-orientation"],
    });

    setView(panelState.mobileWorkspaceView);

    function setView(requestedView) {
        const view = normalizeView(requestedView);
        panelState.mobileWorkspaceView = view;
        DOM.pageShell.dataset.mobileWorkspaceView = view;

        if (usesTabbedWorkspace() && view === "operations" && DOM.settingsPanel) {
            DOM.settingsPanel.open = true;
        }

        if (usesTabbedWorkspace()) {
            onViewChange(view);
        }

        render();
    }

    function syncLayoutMode() {
        render();
    }

    function render() {
        const isTabbedWorkspace = usesTabbedWorkspace();
        const activeView = normalizeView(panelState.mobileWorkspaceView);
        DOM.consoleMobileWorkspaceTabs.setAttribute("aria-hidden", String(!isTabbedWorkspace));

        tabs.forEach(({ button, view }) => {
            const selected = view === activeView;
            button.setAttribute("aria-selected", String(selected));
            button.tabIndex = selected ? 0 : -1;
        });

        regions.forEach(({ region, view }) => {
            if (!isTabbedWorkspace) {
                region.removeAttribute("aria-hidden");
                region.removeAttribute("aria-labelledby");
                region.removeAttribute("role");
                region.inert = false;
                return;
            }

            const selected = view === activeView;
            const tab = tabs.find((entry) => entry.view === view)?.button;
            region.setAttribute("role", "tabpanel");
            region.setAttribute("aria-hidden", String(!selected));
            if (tab) {
                region.setAttribute("aria-labelledby", tab.id);
            }
            region.inert = !selected;
        });
    }

    function usesTabbedWorkspace() {
        const layoutMode = root.dataset.layoutMode;
        const viewportOrientation = root.dataset.viewportOrientation;
        // Compact workspace when data-layout-mode === "tablet" and
        // data-viewport-orientation !== "landscape", or on mobile.
        return layoutMode === "mobile"
            || (layoutMode === "tablet" && viewportOrientation !== "landscape");
    }

    function handleTabKeydown(event, currentView) {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            return;
        }

        event.preventDefault();
        const currentIndex = WORKSPACE_VIEWS.indexOf(currentView);
        let nextIndex = currentIndex;
        if (event.key === "ArrowLeft") {
            nextIndex = currentIndex <= 0 ? WORKSPACE_VIEWS.length - 1 : currentIndex - 1;
        }
        if (event.key === "ArrowRight") {
            nextIndex = currentIndex >= WORKSPACE_VIEWS.length - 1 ? 0 : currentIndex + 1;
        }
        if (event.key === "Home") {
            nextIndex = 0;
        }
        if (event.key === "End") {
            nextIndex = WORKSPACE_VIEWS.length - 1;
        }

        const nextView = WORKSPACE_VIEWS[nextIndex];
        setView(nextView);
        tabs.find((entry) => entry.view === nextView)?.button.focus();
    }

    return {
        destroy() {
            layoutObserver.disconnect();
        },
        refresh: syncLayoutMode,
        setView,
    };
}

function workspaceTabs() {
    return [
        { button: DOM.consoleMobileWorkspaceTabStage, view: "stage" },
        { button: DOM.consoleMobileWorkspaceTabOperations, view: "operations" },
        { button: DOM.consoleMobileWorkspaceTabChat, view: "chat" },
    ].filter((entry) => entry.button);
}

function workspaceRegions() {
    return [
        { region: DOM.consoleStageWorkspace, view: "stage" },
        { region: DOM.consoleOperationsWorkspace, view: "operations" },
        { region: DOM.consoleChatWorkspace, view: "chat" },
    ].filter((entry) => entry.region);
}

function normalizeView(view) {
    return WORKSPACE_VIEWS.includes(view) ? view : "stage";
}

function createNoopController() {
    return {
        destroy() {},
        refresh() {},
        setView() {},
    };
}

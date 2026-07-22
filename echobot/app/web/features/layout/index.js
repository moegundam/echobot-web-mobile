import { createCronController } from "./cron.js?v=site-public-6";
import { createHeartbeatController } from "./heartbeat.js?v=site-public-6";
import { createPanelController } from "./panels.js?v=console-layout-1";
import { createRuntimeController } from "./runtime.js";
import { createSidebarController } from "./sidebars.js?v=site-public-12";
import { createSplitController } from "./split.js?v=console-layout-1";

export function createLayoutModule(deps) {
    let cron;
    let heartbeat;

    const panels = createPanelController({
        handleCronPanelToggle() {
            cron.handleCronPanelToggle();
        },
        handleHeartbeatPanelToggle() {
            heartbeat.handleHeartbeatPanelToggle();
        },
    });
    const sidebars = createSidebarController({ t: deps.t });
    const split = createSplitController();
    const runtime = createRuntimeController(deps);
    cron = createCronController({
        formatTimestamp: deps.formatTimestamp,
        isSettingsPanelOpen: panels.isSettingsPanelOpen,
        requestJson: deps.requestJson,
        setRunStatus: deps.setRunStatus,
        t: deps.t,
    });
    heartbeat = createHeartbeatController({
        isSettingsPanelOpen: panels.isSettingsPanelOpen,
        requestJson: deps.requestJson,
        t: deps.t,
    });

    return {
        ...cron,
        ...heartbeat,
        ...panels,
        ...runtime,
        ...sidebars,
        ...split,
        refreshLocalizedText() {
            sidebars.refreshSidebarLabels?.();
            cron.refreshLocalizedText?.();
            heartbeat.refreshLocalizedText?.();
        },
    };
}

import { initShellI18n } from "./shell-i18n.js?v=ux-public-1&uiux=2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";
import { requestJson } from "./modules/api.js";

const healthElements = {
    output: document.getElementById("admin-health-output"),
    updated: document.getElementById("admin-health-updated"),
    refresh: document.getElementById("admin-health-refresh"),
    status: document.getElementById("admin-health-status"),
    session: document.getElementById("admin-health-session"),
    role: document.getElementById("admin-health-role"),
    channels: document.getElementById("admin-health-channels"),
    jobs: document.getElementById("admin-health-jobs"),
};
let healthSnapshot = null;
let healthErrorMessage = "";
let healthUpdatedAt = null;
const i18n = initShellI18n({
    onChange: () => {
        refreshLocalizedAdminText();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
initShellSessionLinks();

healthElements.refresh?.addEventListener("click", loadHealthSnapshot);
void loadHealthSnapshot();

async function loadHealthSnapshot() {
    if (!healthElements.output) {
        return;
    }

    healthErrorMessage = "";
    healthElements.refresh.disabled = true;
    healthElements.refresh.setAttribute("aria-busy", "true");
    healthElements.output.textContent = i18n.t("admin.loading");
    try {
        const payload = await requestJson("/api/health");
        healthSnapshot = safeHealthSnapshot(payload);
        healthUpdatedAt = new Date();
        renderHealthSnapshot();
    } catch (error) {
        healthSnapshot = null;
        healthErrorMessage = error.message || String(error);
        renderHealthSnapshot();
    } finally {
        healthElements.refresh.disabled = false;
        healthElements.refresh.removeAttribute("aria-busy");
    }
}

function safeHealthSnapshot(payload) {
    const channels = payload && typeof payload.channels === "object" && payload.channels
        ? Object.fromEntries(
            Object.entries(payload.channels).map(([name, value]) => [
                name,
                {
                    enabled: Boolean(value && value.enabled),
                    running: Boolean(value && value.running),
                },
            ]),
        )
        : {};
    const jobs = payload && typeof payload.jobs === "object" && payload.jobs ? payload.jobs : {};
    return {
        status: payload && payload.status ? String(payload.status) : "",
        current_session: payload && payload.current_session ? String(payload.current_session) : "",
        current_role: payload && payload.current_role ? String(payload.current_role) : "",
        channels,
        jobs,
    };
}

function renderHealthSnapshot() {
    if (!healthElements.output) {
        return;
    }

    if (healthErrorMessage) {
        healthElements.output.textContent = i18n.t("admin.healthFailed", {
            message: healthErrorMessage,
        });
        healthElements.status.textContent = i18n.t("admin.unknown");
        healthElements.status.dataset.state = "error";
        healthElements.session.textContent = i18n.t("runtimeContext.notSet");
        healthElements.role.textContent = i18n.t("runtimeContext.notSet");
        healthElements.channels.textContent = i18n.t("admin.unknown");
        healthElements.jobs.textContent = i18n.t("admin.unknown");
        renderUpdatedAt();
        return;
    }

    if (!healthSnapshot) {
        healthElements.output.textContent = i18n.t("admin.loading");
        return;
    }

    const channelValues = Object.values(healthSnapshot.channels);
    const enabledChannels = channelValues.filter((channel) => channel.enabled).length;
    const runningChannels = channelValues.filter((channel) => channel.running).length;
    const jobValues = Object.values(healthSnapshot.jobs).map((value) => Number(value) || 0);
    const totalJobs = jobValues.reduce((total, count) => total + count, 0);
    const activeJobs = (Number(healthSnapshot.jobs.running) || 0)
        + (Number(healthSnapshot.jobs.waiting_for_input) || 0);

    healthElements.status.textContent = healthSnapshot.status === "ok"
        ? i18n.t("admin.healthOk")
        : (healthSnapshot.status || i18n.t("admin.unknown"));
    healthElements.status.dataset.state = healthSnapshot.status === "ok" ? "ok" : "error";
    healthElements.session.textContent = healthSnapshot.current_session || i18n.t("runtimeContext.notSet");
    healthElements.role.textContent = healthSnapshot.current_role || i18n.t("runtimeContext.notSet");
    healthElements.channels.textContent = i18n.t("admin.healthChannelsSummary", {
        running: runningChannels,
        enabled: enabledChannels,
    });
    healthElements.jobs.textContent = i18n.t("admin.healthJobsSummary", {
        active: activeJobs,
        total: totalJobs,
    });
    healthElements.output.textContent = i18n.t("admin.healthReady");
    renderUpdatedAt();
}

function renderUpdatedAt() {
    if (!healthElements.updated) {
        return;
    }
    if (!healthUpdatedAt) {
        healthElements.updated.textContent = i18n.t("admin.healthNotUpdated");
        healthElements.updated.removeAttribute("datetime");
        return;
    }
    const locale = document.documentElement.lang || "en";
    const formattedTime = new Intl.DateTimeFormat(locale, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    }).format(healthUpdatedAt);
    healthElements.updated.dateTime = healthUpdatedAt.toISOString();
    healthElements.updated.textContent = i18n.t("admin.healthUpdated", {
        time: formattedTime,
    });
}

function refreshLocalizedAdminText() {
    renderHealthSnapshot();
}

import { DOM } from "../../core/dom.js";
import { panelState, CRON_POLL_INTERVAL_MS } from "../../core/store.js";
import { writeCronPanelState } from "./panels.js";

export function createCronController(deps) {
    const {
        formatTimestamp,
        isSettingsPanelOpen,
        requestJson,
        setRunStatus = () => {},
        t = (key) => key,
    } = deps;
    let lastStatusPayload = null;
    let lastJobs = null;

    function handleCronPanelToggle() {
        if (!DOM.cronPanel || !DOM.cronSummaryText) {
            return;
        }

        const isExpanded = DOM.cronPanel.open;
        const settingsPanelOpen = isSettingsPanelOpen();
        writeCronPanelState(isExpanded);

        if (!isExpanded || !settingsPanelOpen) {
            stopCronPolling();
            DOM.cronSummaryText.textContent = isExpanded ? t("console.expanded") : t("console.hidden");
            if (DOM.cronStatus) {
                DOM.cronStatus.textContent = settingsPanelOpen
                    ? t("console.cronLoadAfterExpand")
                    : t("console.cronOpenSettingsFirst");
            }
            return;
        }

        DOM.cronSummaryText.textContent = t("console.loadingEllipsis");
        void refreshCronPanel();
        startCronPolling();
    }

    function startCronPolling() {
        stopCronPolling();
        panelState.cronPollTimerId = window.setInterval(() => {
            if (!DOM.cronPanel || !DOM.cronPanel.open || !isSettingsPanelOpen()) {
                return;
            }
            void refreshCronPanel();
        }, CRON_POLL_INTERVAL_MS);
    }

    function stopCronPolling() {
        if (!panelState.cronPollTimerId) {
            return;
        }

        window.clearInterval(panelState.cronPollTimerId);
        panelState.cronPollTimerId = 0;
    }

    async function refreshCronPanel() {
        if (!DOM.cronPanel || !DOM.cronPanel.open || !isSettingsPanelOpen() || panelState.cronLoading) {
            return;
        }

        try {
            setCronPanelLoading(true, t("console.cronLoading"));
            const { statusPayload, jobs } = await loadCronPanelData();
            renderCronPanel(statusPayload, jobs);
        } catch (error) {
            console.error(error);
            if (DOM.cronSummaryText) {
                DOM.cronSummaryText.textContent = t("console.loadFailed");
            }
            if (DOM.cronStatus) {
                DOM.cronStatus.textContent = error.message || t("console.cronLoadFailed");
            }
        } finally {
            setCronPanelLoading(false);
        }
    }

    async function loadCronPanelData() {
        const [statusPayload, jobsPayload] = await Promise.all([
            requestJson("/api/cron/status"),
            requestJson("/api/cron/jobs?include_disabled=true"),
        ]);
        return {
            statusPayload: statusPayload,
            jobs: jobsPayload.jobs || [],
        };
    }

    function renderCronPanel(statusPayload, jobs) {
        lastStatusPayload = statusPayload || null;
        lastJobs = Array.isArray(jobs) ? jobs : [];
        if (DOM.cronSummaryText) {
            DOM.cronSummaryText.textContent = buildCronSummaryText(statusPayload, jobs);
        }
        if (DOM.cronStatus) {
            DOM.cronStatus.textContent = buildCronStatusText(statusPayload, jobs);
        }
        renderCronJobs(jobs);
    }

    function buildCronSummaryText(statusPayload, jobs) {
        if (!statusPayload.enabled) {
            return t("console.schedulerStopped");
        }
        if (!jobs || jobs.length === 0) {
            return t("console.noJobs");
        }
        return t("console.jobCount", { count: jobs.length });
    }

    function buildCronStatusText(statusPayload, jobs) {
        const statusText = statusPayload.enabled ? t("console.schedulerRunning") : t("console.schedulerStopped");
        if (!jobs || jobs.length === 0) {
            return `${statusText} · ${t("console.cronEmpty")}`;
        }

        const nextRunText = formatTimestamp(statusPayload.next_run_at);
        if (!nextRunText) {
            return `${statusText} · ${t("console.totalJobs", { count: jobs.length })}`;
        }
        return `${statusText} · ${t("console.totalJobs", { count: jobs.length })} · ${t("console.nextRun", { time: nextRunText })}`;
    }

    function renderCronJobs(jobs) {
        if (!DOM.cronJobs) {
            return;
        }

        DOM.cronJobs.innerHTML = "";
        if (!jobs || jobs.length === 0) {
            const empty = document.createElement("p");
            empty.className = "cron-empty";
            empty.textContent = t("console.cronEmpty");
            DOM.cronJobs.appendChild(empty);
            return;
        }

        jobs.forEach((job) => {
            DOM.cronJobs.appendChild(buildCronJobCard(job));
        });
    }

    function buildCronJobCard(job) {
        const container = document.createElement("article");
        container.className = "cron-job";

        const header = document.createElement("div");
        header.className = "cron-job-header";

        const title = document.createElement("h3");
        title.className = "cron-job-title";
        title.textContent = job.name || t("console.unnamedJob");

        const idText = document.createElement("span");
        idText.className = "cron-job-id";
        idText.textContent = `#${job.id || "-"}`;

        header.appendChild(title);
        header.appendChild(idText);

        const meta = document.createElement("div");
        meta.className = "cron-job-meta";
        meta.appendChild(buildCronBadge(job.enabled ? t("console.enabled") : t("console.disabled"), job.enabled ? "enabled" : "disabled"));
        meta.appendChild(buildCronBadge(buildCronLastStatusLabel(job.last_status), cronStatusClassName(job.last_status)));
        meta.appendChild(buildCronMetaText(t("console.scheduleMeta", { value: job.schedule || "-" })));
        meta.appendChild(buildCronMetaText(t("console.sessionMeta", { value: job.session_name || "-" })));
        meta.appendChild(buildCronMetaText(t("console.typeMeta", { value: job.payload_kind || "-" })));

        const times = document.createElement("div");
        times.className = "cron-job-times";
        times.appendChild(buildCronMetaText(t("console.nextMeta", { value: formatTimestamp(job.next_run_at) || "-" })));
        times.appendChild(buildCronMetaText(t("console.previousMeta", { value: formatTimestamp(job.last_run_at) || "-" })));

        container.appendChild(header);
        container.appendChild(meta);
        container.appendChild(times);

        const actions = document.createElement("div");
        actions.className = "cron-job-actions";

        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.className = "ghost-button ghost-button-compact ghost-button-danger";
        cancelButton.textContent = t("console.cancel");
        cancelButton.disabled = panelState.cronLoading || !job.id;
        cancelButton.addEventListener("click", () => {
            void handleCancelCronJob(job);
        });

        actions.appendChild(cancelButton);
        container.appendChild(actions);

        if (job.last_error) {
            const error = document.createElement("div");
            error.className = "cron-job-error";
            error.textContent = t("console.errorMeta", { value: job.last_error });
            container.appendChild(error);
        }

        return container;
    }

    async function handleCancelCronJob(job) {
        const jobId = String(job?.id || "").trim();
        if (!jobId || panelState.cronLoading) {
            return;
        }

        const jobName = String(job?.name || t("console.unnamedJob"));
        if (!window.confirm(t("console.cancelCronConfirm", { job: jobName }))) {
            return;
        }

        try {
            setCronPanelLoading(true, t("console.cancellingCronJob", { job: jobName }));
            await requestJson(`/api/cron/jobs/${encodeURIComponent(jobId)}`, {
                method: "DELETE",
            });

            const { statusPayload, jobs } = await loadCronPanelData();
            renderCronPanel(statusPayload, jobs);

            const statusText = t("console.cronJobCancelled", { job: jobName });
            if (DOM.cronStatus) {
                DOM.cronStatus.textContent = statusText;
            }
            setRunStatus(statusText);
        } catch (error) {
            console.error(error);
            const message = error.message || t("console.cancelCronFailed");
            if (DOM.cronStatus) {
                DOM.cronStatus.textContent = message;
            }
            setRunStatus(message);
        } finally {
            setCronPanelLoading(false);
        }
    }

    function setCronPanelLoading(isLoading, statusText = "") {
        panelState.cronLoading = isLoading;
        if (DOM.cronStatus && statusText) {
            DOM.cronStatus.textContent = statusText;
        }
        if (DOM.cronRefreshButton) {
            DOM.cronRefreshButton.disabled = isLoading;
        }
        toggleCronJobButtons(isLoading);
    }

    function toggleCronJobButtons(disabled) {
        if (!DOM.cronJobs) {
            return;
        }

        const buttons = DOM.cronJobs.querySelectorAll("button");
        buttons.forEach((button) => {
            button.disabled = disabled;
        });
    }

    function buildCronBadge(text, kind) {
        const badge = document.createElement("span");
        badge.className = `cron-badge cron-badge-${kind}`;
        badge.textContent = text;
        return badge;
    }

    function buildCronMetaText(text) {
        const item = document.createElement("span");
        item.textContent = text;
        return item;
    }

    function buildCronLastStatusLabel(status) {
        if (status === "ok") {
            return t("console.lastOk");
        }
        if (status === "error") {
            return t("console.lastError");
        }
        if (status === "running") {
            return t("console.running");
        }
        if (status === "skipped") {
            return t("console.skipped");
        }
        return t("console.noStatus");
    }

    function cronStatusClassName(status) {
        if (status === "ok") {
            return "ok";
        }
        if (status === "error") {
            return "error";
        }
        if (status === "running") {
            return "running";
        }
        return "idle";
    }

    return {
        handleCronPanelToggle,
        refreshCronPanel,
        refreshLocalizedText() {
            if (lastStatusPayload) {
                renderCronPanel(lastStatusPayload, lastJobs);
                return;
            }
            if (DOM.cronPanel && DOM.cronSummaryText) {
                const isExpanded = DOM.cronPanel.open;
                DOM.cronSummaryText.textContent = isExpanded ? t("console.expanded") : t("console.hidden");
            }
            if (DOM.cronStatus) {
                DOM.cronStatus.textContent = t("console.cronLoadAfterExpand");
            }
        },
    };
}

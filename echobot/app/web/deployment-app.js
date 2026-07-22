import { initShellI18n } from "./shell-i18n.js?v=ux-public-1&uiux=2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { requestJson } from "./modules/api.js";

const statusGrid = document.getElementById("deployment-status-grid");
const guidedGrid = document.getElementById("deployment-guided-grid");
const commandsOutput = document.getElementById("deployment-commands-output");

let statusPayload = null;
let statusError = "";

const i18n = initShellI18n({
    onChange: () => {
        renderAll();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });

renderAll();
loadDeploymentStatus();

async function loadDeploymentStatus() {
    try {
        statusPayload = await requestJson("/api/deployment/status");
        statusError = "";
    } catch (error) {
        statusPayload = null;
        statusError = error.message || String(error);
    }
    renderAll();
}

function renderAll() {
    renderStatus();
    renderGuidedInputs();
    renderCommands();
}

function renderStatus() {
    if (!statusGrid) {
        return;
    }
    if (statusError) {
        statusGrid.replaceChildren(
            buildStatusCard(
                i18n.t("deployment.statusError"),
                i18n.t("deployment.statusErrorBody", { message: statusError }),
                "danger",
            ),
        );
        return;
    }
    if (!statusPayload) {
        statusGrid.replaceChildren(
            buildStatusCard(
                i18n.t("deployment.loading"),
                i18n.t("deployment.loadingBody"),
                "muted",
            ),
        );
        return;
    }

    const cloudflare = statusPayload.cloudflare || {};
    const githubActions = statusPayload.github_actions || {};
    const openwebui = statusPayload.openwebui || {};
    const local = statusPayload.local || {};
    const cards = [
        buildStatusCard(
            i18n.t("deployment.localHealth"),
            local.health || i18n.t("deployment.unknown"),
            local.health === "ok" ? "ok" : "danger",
        ),
        buildStatusCard(
            i18n.t("deployment.channels"),
            formatChannels(local.channels),
            "mono",
        ),
        buildStatusCard(
            i18n.t("deployment.cloudflared"),
            cloudflare.cli_installed
                ? cloudflare.version || i18n.t("deployment.installed")
                : i18n.t("deployment.missing"),
            cloudflare.cli_installed ? "ok" : "danger",
        ),
        buildStatusCard(
            i18n.t("deployment.originCert"),
            cloudflare.origin_cert_present
                ? cloudflare.origin_cert_path || i18n.t("deployment.present")
                : i18n.t("deployment.missing"),
            cloudflare.origin_cert_present ? "ok" : "warn",
        ),
        buildStatusCard(
            i18n.t("deployment.ciNode"),
            githubActions.node24_ready
                ? i18n.t("deployment.ready")
                : i18n.t("deployment.warning"),
            githubActions.node24_ready ? "ok" : "warn",
        ),
        buildStatusCard(
            i18n.t("deployment.openwebuiToken"),
            openwebui.token_configured
                ? i18n.t("deployment.configured")
                : i18n.t("deployment.missing"),
            openwebui.token_configured ? "ok" : "warn",
        ),
    ];

    for (const item of statusPayload.readiness || []) {
        cards.push(
            buildStatusCard(
                translatedPayloadText(item.name_key, item.name || i18n.t("deployment.readiness")),
                translatedPayloadText(item.detail_key, item.detail || item.status || ""),
                statusTone(item.status),
            ),
        );
    }
    statusGrid.replaceChildren(...cards);
}

function renderGuidedInputs() {
    if (!guidedGrid) {
        return;
    }
    const futureInputs = statusPayload && statusPayload.simple_deploy
        ? statusPayload.simple_deploy.future_inputs || []
        : ["hostname", "access_emails", "local_port", "tunnel_name", "target_user_id"];
    guidedGrid.replaceChildren(
        ...futureInputs.map((item) => {
            const row = document.createElement("label");
            row.className = "deployment-guided-field";
            const label = document.createElement("span");
            label.textContent = deploymentInputLabel(item);
            const input = document.createElement("input");
            input.type = "text";
            input.disabled = true;
            input.placeholder = i18n.t("deployment.guidedPlaceholder");
            row.append(label, input);
            return row;
        }),
    );
}

function renderCommands() {
    if (!commandsOutput) {
        return;
    }
    if (!statusPayload) {
        commandsOutput.textContent = statusError
            ? i18n.t("deployment.statusErrorBody", { message: statusError })
            : i18n.t("deployment.loading");
        return;
    }
    const lines = [];
    for (const command of statusPayload.commands || []) {
        lines.push(command);
    }
    const cloudflare = statusPayload.cloudflare || {};
    const nextSteps = translatedNextSteps(cloudflare);
    if (nextSteps.length) {
        lines.push("", i18n.t("deployment.nextSteps"));
        for (const step of nextSteps) {
            lines.push(`- ${step}`);
        }
    }
    commandsOutput.textContent = lines.join("\n");
}

function buildStatusCard(title, value, tone) {
    const card = document.createElement("article");
    card.className = `openwebui-status-card openwebui-status-${tone || "muted"}`;
    const heading = document.createElement("h3");
    heading.textContent = title;
    const body = document.createElement("p");
    body.textContent = value;
    card.append(heading, body);
    return card;
}

function formatChannels(channels) {
    if (!channels || typeof channels !== "object") {
        return i18n.t("deployment.unknown");
    }
    return Object.entries(channels)
        .map(([name, value]) => {
            const running = value && value.running ? i18n.t("deployment.running") : i18n.t("deployment.stopped");
            return `${name}: ${running}`;
        })
        .join(" / ") || i18n.t("deployment.unknown");
}

function deploymentInputLabel(key) {
    return i18n.t(`deployment.input.${key}`) || key;
}

function translatedPayloadText(key, fallback) {
    if (key) {
        const translated = i18n.t(key);
        if (translated !== key) {
            return translated;
        }
    }
    return fallback;
}

function translatedNextSteps(cloudflare) {
    if (Array.isArray(cloudflare.next_step_keys) && cloudflare.next_step_keys.length) {
        return cloudflare.next_step_keys.map((key, index) => {
            return translatedPayloadText(key, (cloudflare.next_steps || [])[index] || key);
        });
    }
    return Array.isArray(cloudflare.next_steps) ? cloudflare.next_steps : [];
}

function statusTone(status) {
    if (status === "ready" || status === "ok") {
        return "ok";
    }
    if (status === "warning") {
        return "warn";
    }
    if (status === "danger" || status === "error") {
        return "danger";
    }
    return "muted";
}

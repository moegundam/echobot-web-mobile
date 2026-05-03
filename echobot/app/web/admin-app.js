import { initShellI18n } from "./shell-i18n.js?v=site-public-6";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

const healthOutput = document.getElementById("admin-health-output");
let healthErrorMessage = "";
let healthLoaded = false;
const i18n = initShellI18n({
    onChange: () => {
        refreshLocalizedAdminText();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
initShellSessionLinks();

loadHealthSnapshot();

async function loadHealthSnapshot() {
    if (!healthOutput) {
        return;
    }

    healthLoaded = false;
    healthErrorMessage = "";
    healthOutput.textContent = i18n.t("admin.loading");
    try {
        const response = await fetch("/api/health", {
            headers: {
                "Accept": "application/json",
            },
        });
        if (!response.ok) {
            throw await responseToError(response);
        }
        const payload = await response.json();
        healthLoaded = true;
        healthOutput.textContent = JSON.stringify(payload, null, 2);
    } catch (error) {
        healthLoaded = false;
        healthErrorMessage = error.message || String(error);
        healthOutput.textContent = i18n.t("admin.healthFailed", {
            message: healthErrorMessage,
        });
    }
}

function refreshLocalizedAdminText() {
    if (!healthOutput || healthLoaded) {
        return;
    }
    if (healthErrorMessage) {
        healthOutput.textContent = i18n.t("admin.healthFailed", {
            message: healthErrorMessage,
        });
        return;
    }
    healthOutput.textContent = i18n.t("admin.loading");
}

async function responseToError(response) {
    let detail = `${response.status} ${response.statusText}`;
    try {
        const payload = await response.json();
        if (payload && typeof payload.detail === "string") {
            detail = payload.detail;
        }
    } catch (_error) {
        return new Error(detail);
    }
    return new Error(detail);
}

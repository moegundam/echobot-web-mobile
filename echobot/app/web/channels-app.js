import { initShellI18n } from "./shell-i18n.js?v=site-public-6";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

const PLANNED_CHANNELS = [
    { name: "line", label: "LINE" },
    { name: "discord", label: "Discord" },
    { name: "whatsapp", label: "WhatsApp" },
];

const channelText = {
    en: {
        builtInTitle: "Available runtime channels",
        builtInBody: "These channels already exist in the EchoBot runtime registry. This page is read-only for now so secrets are not entered into an unfinished UI.",
        plannedTitle: "Planned messaging integrations",
        plannedBody: "These gateways should be added here before they are wired to runtime adapters.",
        rulesTitle: "Integration rules",
        rulesBody: "Keep public messaging platforms separate from Open WebUI. Open WebUI is an operator workbench; channels are public or semi-public gateways.",
        rules: [
            "Start every new platform with status, config fields, and a smoke-test checklist on this page.",
            "Store bot tokens and secrets outside the repo; the UI must mask values and never echo plaintext tokens.",
            "Default external user traffic to chat-only until an approval gate exists for tool-capable Agent work.",
            "Verify webhook signatures or polling identity before accepting inbound messages.",
        ],
        descriptions: {
            console: "Local console output channel for smoke testing.",
            telegram: "Telegram bot polling channel.",
            qq: "QQ official bot direct-message channel.",
        },
    },
    "zh-Hant": {
        builtInTitle: "目前可用 runtime channels",
        builtInBody: "這些 channel 已存在於 EchoBot runtime registry。此頁目前先做只讀狀態與設定邊界，避免在未完成 UI 中輸入 secrets。",
        plannedTitle: "規劃中的通訊平台整合",
        plannedBody: "這些 gateway 應先在此頁建立設定邊界，再接 runtime adapter。",
        rulesTitle: "整合規則",
        rulesBody: "公開通訊平台要和 Open WebUI 分開。Open WebUI 是操作員工作台；channels 是公開或半公開 gateway。",
        rules: [
            "每個新平台先在此頁補狀態、設定欄位與 smoke-test checklist。",
            "Bot token 與 secrets 放 repo 外；UI 必須遮罩，不回顯明文 token。",
            "外部使用者流量預設 chat-only，等 approval gate 完成後才開工具型 Agent。",
            "接收 inbound message 前必須驗證 webhook 簽章或 polling 身分。",
        ],
        descriptions: {
            console: "本機 console output channel，用於 smoke test。",
            telegram: "Telegram bot polling channel。",
            qq: "QQ 官方 bot direct-message channel。",
        },
    },
    "zh-Hans": {
        builtInTitle: "当前可用 runtime channels",
        builtInBody: "这些 channel 已存在于 EchoBot runtime registry。此页目前先做只读状态与设置边界，避免在未完成 UI 中输入 secrets。",
        plannedTitle: "规划中的通讯平台整合",
        plannedBody: "这些 gateway 应先在此页建立设置边界，再接 runtime adapter。",
        rulesTitle: "整合规则",
        rulesBody: "公开通讯平台要和 Open WebUI 分开。Open WebUI 是操作员工作台；channels 是公开或半公开 gateway。",
        rules: [
            "每个新平台先在此页补状态、设置字段与 smoke-test checklist。",
            "Bot token 与 secrets 放 repo 外；UI 必须遮罩，不回显明文 token。",
            "外部使用者流量默认 chat-only，等 approval gate 完成后才开工具型 Agent。",
            "接收 inbound message 前必须验证 webhook 签章或 polling 身分。",
        ],
        descriptions: {
            console: "本机 console output channel，用于 smoke test。",
            telegram: "Telegram bot polling channel。",
            qq: "QQ 官方 bot direct-message channel。",
        },
    },
};

const state = {
    definitions: [],
    config: {},
    status: {},
    error: "",
    loaded: false,
};

const statusGrid = document.getElementById("channels-status-grid");
const contentRoot = document.getElementById("channels-content");

const i18n = initShellI18n({
    onChange: () => {
        renderAll();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
initShellSessionLinks();

renderAll();
void loadChannels();

async function loadChannels() {
    state.loaded = false;
    state.error = "";
    renderAll();
    try {
        const [definitions, config, status] = await Promise.all([
            requestJson("/api/channels/definitions"),
            requestJson("/api/channels/config"),
            requestJson("/api/channels/status"),
        ]);
        state.definitions = Array.isArray(definitions) ? definitions : [];
        state.config = config && typeof config === "object" ? config : {};
        state.status = status && typeof status === "object" ? status : {};
        state.loaded = true;
    } catch (error) {
        state.error = error.message || String(error);
        state.loaded = false;
    }
    renderAll();
}

function renderAll() {
    renderStatus();
    renderContent();
}

function renderStatus() {
    if (!statusGrid) {
        return;
    }
    if (state.error) {
        statusGrid.replaceChildren(buildStatusCard(
            i18n.t("channels.errorTitle"),
            i18n.t("channels.errorBody", { message: state.error }),
            "danger",
        ));
        return;
    }
    if (!state.loaded) {
        statusGrid.replaceChildren(buildStatusCard(
            i18n.t("channels.loading"),
            i18n.t("channels.loadingBody"),
            "muted",
        ));
        return;
    }

    const cards = state.definitions.map((definition) => {
        const channelName = String(definition.name || "");
        const config = channelConfig(channelName);
        const enabled = Boolean(config.enabled);
        const running = channelIsRunning(channelName);
        const detail = [
            enabled ? i18n.t("channels.enabled") : i18n.t("channels.disabled"),
            running ? i18n.t("channels.running") : i18n.t("channels.stopped"),
        ].join(" · ");
        return buildStatusCard(
            channelLabel(channelName),
            detail,
            running ? "ok" : enabled ? "warn" : "muted",
        );
    });
    statusGrid.replaceChildren(...cards);
}

function renderContent() {
    if (!contentRoot) {
        return;
    }
    const content = currentText();
    contentRoot.replaceChildren(
        buildChannelSection(
            content.builtInTitle,
            content.builtInBody,
            state.definitions.map((definition) => channelCardFromDefinition(definition)),
        ),
        buildChannelSection(
            content.plannedTitle,
            content.plannedBody,
            PLANNED_CHANNELS.map((channel) => plannedChannelCard(channel)),
        ),
        buildRuleSection(content),
    );
}

function channelCardFromDefinition(definition) {
    const channelName = String(definition.name || "");
    const fields = Array.isArray(definition.config_fields)
        ? definition.config_fields
        : [];
    return {
        label: channelLabel(channelName),
        owner: channelConfig(channelName).enabled
            ? i18n.t("channels.enabled")
            : i18n.t("channels.disabled"),
        route: `/api/channels/config:${channelName}`,
        purpose: currentText().descriptions[channelName] || String(definition.description || ""),
        fields: fields.map((field) => String(field.name || "")).filter(Boolean),
    };
}

function plannedChannelCard(channel) {
    return {
        label: channel.label,
        owner: i18n.t("channels.planned"),
        route: `/admin/channels:${channel.name}`,
        purpose: i18n.t("channels.plannedPurpose"),
        fields: [
            "enabled",
            "allow_from",
            "bot_token / webhook_secret",
            "webhook_url / polling",
        ],
    };
}

function buildChannelSection(titleText, bodyText, cards) {
    const section = document.createElement("section");
    section.className = "structure-section";

    const title = document.createElement("h2");
    title.textContent = titleText;
    const body = document.createElement("p");
    body.className = "structure-section-body";
    body.textContent = bodyText;

    const grid = document.createElement("div");
    grid.className = "structure-card-grid";
    grid.replaceChildren(...cards.map((card) => buildChannelCard(card)));

    section.append(title, body, grid);
    return section;
}

function buildChannelCard(card) {
    const article = document.createElement("article");
    article.className = "structure-card";

    const header = document.createElement("div");
    header.className = "structure-card-header";
    const title = document.createElement("h3");
    title.textContent = card.label;
    const owner = document.createElement("span");
    owner.className = "structure-owner";
    owner.textContent = card.owner;
    header.append(title, owner);

    const route = document.createElement("code");
    route.className = "structure-route";
    route.textContent = card.route;

    const purpose = document.createElement("p");
    purpose.textContent = card.purpose;

    const fields = document.createElement("p");
    fields.className = "channels-field-list";
    fields.textContent = `${i18n.t("channels.configFields")}: ${card.fields.join(", ") || i18n.t("channels.none")}`;

    article.append(header, route, purpose, fields);
    return article;
}

function buildRuleSection(content) {
    const section = document.createElement("section");
    section.className = "structure-section";

    const title = document.createElement("h2");
    title.textContent = content.rulesTitle;
    const body = document.createElement("p");
    body.className = "structure-section-body";
    body.textContent = content.rulesBody;
    const list = document.createElement("ul");
    list.className = "structure-rule-list";
    content.rules.forEach((rule) => {
        const item = document.createElement("li");
        item.textContent = rule;
        list.appendChild(item);
    });

    section.append(title, body, list);
    return section;
}

function buildStatusCard(titleText, valueText, tone) {
    const article = document.createElement("article");
    article.className = `openwebui-status-card openwebui-status-${tone}`;
    const title = document.createElement("h3");
    title.textContent = titleText;
    const value = document.createElement("p");
    value.textContent = valueText;
    article.append(title, value);
    return article;
}

function channelConfig(channelName) {
    const config = state.config[channelName];
    return config && typeof config === "object" ? config : {};
}

function channelIsRunning(channelName) {
    const status = state.status[channelName];
    if (!status || typeof status !== "object") {
        return false;
    }
    return Object.values(status).some(Boolean);
}

function channelLabel(channelName) {
    if (channelName === "qq") {
        return "QQ";
    }
    return channelName
        ? `${channelName.charAt(0).toUpperCase()}${channelName.slice(1)}`
        : i18n.t("channels.unknown");
}

function currentText() {
    return channelText[i18n.language] || channelText.en;
}

async function requestJson(url) {
    const response = await fetch(url, {
        headers: {
            Accept: "application/json",
        },
    });
    if (!response.ok) {
        let detail = `${response.status} ${response.statusText}`;
        try {
            const payload = await response.json();
            detail = payload.detail || detail;
        } catch (_error) {
            // Keep the HTTP status fallback for non-JSON responses.
        }
        throw new Error(detail);
    }
    return response.json();
}

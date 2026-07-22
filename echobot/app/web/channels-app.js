import { initShellI18n } from "./shell-i18n.js?v=language-menu-1&uiux=2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";
import { requestJson } from "./modules/api.js";

const PLANNED_CHANNELS = [
    { name: "line", label: "LINE" },
    { name: "whatsapp", label: "WhatsApp" },
];

const EDITABLE_CHANNELS = new Set(["telegram", "discord"]);

const FALLBACK_FIELDS = {
    telegram: [
        { name: "allow_from", kind: "textarea" },
        { name: "mirror_to_stage", kind: "bool" },
        { name: "stage_session_name", kind: "text" },
        { name: "bot_token", kind: "secret" },
        { name: "proxy", kind: "text" },
        { name: "reply_to_message", kind: "bool" },
        { name: "drop_pending_updates", kind: "bool" },
    ],
    discord: [
        { name: "allow_from", kind: "textarea" },
        { name: "mirror_to_stage", kind: "bool" },
        { name: "stage_session_name", kind: "text" },
        { name: "bot_token", kind: "secret" },
        { name: "webhook_url", kind: "secret" },
        { name: "webhook_secret", kind: "secret" },
        { name: "application_id", kind: "text" },
        { name: "guild_id", kind: "text" },
        { name: "channel_id", kind: "text" },
    ],
};

const FIELD_LABEL_KEYS = {
    enabled: "channels.fieldEnabled",
    allow_from: "channels.fieldAllowFrom",
    mirror_to_stage: "channels.fieldMirrorToStage",
    stage_session_name: "channels.fieldStageSessionName",
    bot_token: "channels.fieldBotToken",
    proxy: "channels.fieldProxy",
    reply_to_message: "channels.fieldReplyToMessage",
    drop_pending_updates: "channels.fieldDropPendingUpdates",
    webhook_secret: "channels.fieldWebhookSecret",
    webhook_url: "channels.fieldWebhookUrl",
    channel_id: "channels.fieldChannelId",
    api_id: "channels.fieldApiId",
    app_id: "channels.fieldAppId",
    application_id: "channels.fieldApplicationId",
    guild_id: "channels.fieldGuildId",
};

const channelText = {
    en: {
        builtInTitle: "Available runtime channels",
        builtInBody: "Telegram and Discord are editable here for configuration and smoke testing. Other channels remain in a read-only state on this page.",
        verificationTitle: "Platform evidence status",
        verificationBody: "Adapter tests, local routing smoke, historical maintainer evidence, and fresh external acceptance are separate evidence levels.",
        verificationItems: [
            "Telegram: adapter tests and historical maintainer smoke exist; run a fresh external E2E for this deployment.",
            "Discord: adapter tests and historical maintainer smoke exist; run a fresh external E2E for this deployment.",
            "QQ: runtime adapter exists, but no long-running real-platform check has been completed.",
            "LINE / WhatsApp: planning entries only; runtime adapters are not wired yet.",
        ],
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
            discord: "Discord native bot events, protected webhook bridge, and outbound webhook delivery.",
            qq: "QQ official bot direct-message channel.",
        },
        channelHints: {
            telegram: [
                "Inbound uses Bot API polling. Run only one EchoBot poller for the same bot token.",
                "Keep drop pending updates enabled for clean smoke tests; disable it only when you intentionally want queued Telegram messages.",
                "Use the local routing smoke to inject a controlled message; it does not prove a real Telegram platform event.",
            ],
            discord: [
                "Inbound bridge endpoint: POST /api/channels/discord/webhook",
                "Required header: X-EchoBot-Discord-Secret",
                "Request JSON includes channel_id, user_id, text, and optional session_name.",
                "Outbound replies use webhook_url when configured.",
                "Native bot events require discord.py plus Message Content Intent in the Discord Developer Portal.",
                "Use the local routing smoke for Session routing and Stage mirroring before a separate real Discord acceptance run.",
            ],
        },
    },
    "zh-Hant": {
        builtInTitle: "目前可用通訊入口",
        builtInBody: "Telegram 與 Discord 在此頁可編輯並可做連線檢查；其他通訊入口目前仍維持唯讀。",
        verificationTitle: "平台證據狀態",
        verificationBody: "Adapter 測試、本機路由 smoke、歷史維護者證據與本次部署的外部驗收是不同證據層級。",
        verificationItems: [
            "Telegram：已有 adapter 測試與歷史維護者 smoke；本次部署仍需 fresh external E2E。",
            "Discord：已有 adapter 測試與歷史維護者 smoke；本次部署仍需 fresh external E2E。",
            "QQ：已有 runtime adapter，但尚未完成真實平台長跑檢查。",
            "LINE / WhatsApp：目前只是規劃入口，runtime adapter 尚未接線。",
        ],
        plannedTitle: "規劃中的通訊平台整合",
        plannedBody: "這些通訊入口應先在此頁建立設定邊界，再接 runtime adapter。",
        rulesTitle: "整合規則",
        rulesBody: "公開通訊平台要和 Open WebUI 分開。Open WebUI 是操作員工作台；通訊入口是公開或半公開入口。",
        rules: [
            "每個新平台先在此頁補狀態、設定欄位與連線檢查清單。",
            "Bot token 與 secrets 放 repo 外；UI 必須遮罩，不回顯明文 token。",
            "外部使用者流量預設 chat-only，等 approval gate 完成後才開工具型 Agent。",
            "接收外部訊息前必須驗證 webhook 簽章或 polling 身分。",
        ],
        descriptions: {
            console: "本機 console 輸出入口，用於連線檢查。",
            telegram: "Telegram bot polling 通訊入口。",
            discord: "Discord 原生 bot events、受保護 webhook bridge 與 outbound webhook 發送。",
            qq: "QQ 官方 bot 私訊入口；adapter 已存在，但尚未完成真實平台長跑驗證。",
        },
        channelHints: {
            telegram: [
                "Inbound 使用 Bot API polling；同一個 bot token 同時間只能跑一個 EchoBot poller。",
                "乾淨連線檢查建議維持啟動時丟棄 pending updates；只有刻意要吃 Telegram 佇列訊息時才關閉。",
                "可先用本機路由 smoke 注入受控訊息；這不代表已收到真實 Telegram 平台事件。",
            ],
            discord: [
                "Inbound bridge endpoint：POST /api/channels/discord/webhook",
                "必要 header：X-EchoBot-Discord-Secret",
                "Request JSON 包含 channel_id、user_id、text，可選 session_name。",
                "Outbound 回覆在設定 webhook_url 後會透過 Discord webhook 發送。",
                "原生 bot events 需要 discord.py，並在 Discord Developer Portal 開啟 Message Content Intent。",
                "在共享伺服器啟用前，先做本機路由 smoke，再另外執行真實 Discord 驗收。",
            ],
        },
    },
    "zh-Hans": {
        builtInTitle: "当前可用通讯入口",
        builtInBody: "Telegram 与 Discord 在此页可编辑并可做连线检查；其他通讯入口目前仍保持只读。",
        verificationTitle: "平台证据状态",
        verificationBody: "Adapter 测试、本机路由 smoke、历史维护者证据与本次部署的外部验收是不同证据层级。",
        verificationItems: [
            "Telegram：已有 adapter 测试与历史维护者 smoke；本次部署仍需 fresh external E2E。",
            "Discord：已有 adapter 测试与历史维护者 smoke；本次部署仍需 fresh external E2E。",
            "QQ：已有 runtime adapter，但尚未完成真实平台长跑检查。",
            "LINE / WhatsApp：目前只是规划入口，runtime adapter 尚未接线。",
        ],
        plannedTitle: "规划中的通讯平台整合",
        plannedBody: "这些通讯入口应先在此页建立设置边界，再接 runtime adapter。",
        rulesTitle: "整合规则",
        rulesBody: "公开通讯平台要和 Open WebUI 分开。Open WebUI 是操作员工作台；通讯入口是公开或半公开入口。",
        rules: [
            "每个新平台先在此页补状态、设置字段与连线检查清单。",
            "Bot token 与 secrets 放 repo 外；UI 必须遮罩，不回显明文 token。",
            "外部用户流量默认 chat-only，等 approval gate 完成后才开工具型 Agent。",
            "接收外部消息前必须验证 webhook 签章或 polling 身份。",
        ],
        descriptions: {
            console: "本机 console 输出入口，用于连线检查。",
            telegram: "Telegram bot polling 通讯入口。",
            discord: "Discord 原生 bot events、受保护 webhook bridge 与 outbound webhook 发送。",
            qq: "QQ 官方 bot 私信入口；adapter 已存在，但尚未完成真实平台长跑验证。",
        },
        channelHints: {
            telegram: [
                "Inbound 使用 Bot API polling；同一个 bot token 同时间只能跑一个 EchoBot poller。",
                "干净连线检查建议维持启动时丢弃 pending updates；只有刻意要吃 Telegram 队列消息时才关闭。",
                "可先用本机路由 smoke 注入受控消息；这不代表已收到真实 Telegram 平台事件。",
            ],
            discord: [
                "Inbound bridge endpoint：POST /api/channels/discord/webhook",
                "必要 header：X-EchoBot-Discord-Secret",
                "Request JSON 包含 channel_id、user_id、text，可选 session_name。",
                "Outbound 回复在设置 webhook_url 后会通过 Discord webhook 发送。",
                "原生 bot events 需要 discord.py，并在 Discord Developer Portal 开启 Message Content Intent。",
                "在共享服务器启用前，先做本机路由 smoke，再另外执行真实 Discord 验收。",
            ],
        },
    },
};

const state = {
    definitions: [],
    config: {},
    sessions: [],
    status: {},
    error: "",
    loaded: false,
    saving: false,
    smokeInFlight: false,
    messages: {},
    smokeResults: {},
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
        const [definitions, config, status, sessions] = await Promise.all([
            requestJson("/api/channels/definitions"),
            requestJson("/api/channels/config"),
            requestJson("/api/channels/status"),
            requestJson("/api/sessions").catch(() => []),
        ]);
        state.definitions = Array.isArray(definitions) ? definitions : [];
        state.config = config && typeof config === "object" ? config : {};
        state.status = status && typeof status === "object" ? status : {};
        state.sessions = Array.isArray(sessions) ? sessions : [];
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
    const builtInCards = state.definitions.map((definition) => {
        const channelName = String(definition.name || "");
        if (EDITABLE_CHANNELS.has(channelName)) {
            return buildEditableChannelCard(definition);
        }
        return buildChannelCardFromDefinition(definition);
    });
    const builtInText = currentText();

    contentRoot.replaceChildren(
        buildChannelSection(
            builtInText.builtInTitle,
            builtInText.builtInBody,
            builtInCards,
        ),
        buildVerificationSection(builtInText),
        buildChannelSection(
            builtInText.plannedTitle,
            builtInText.plannedBody,
            PLANNED_CHANNELS.map(plannedChannelCard),
        ),
        buildRuleSection(builtInText),
    );
}

function buildVerificationSection(content) {
    const section = document.createElement("section");
    section.className = "structure-section";

    const title = document.createElement("h2");
    title.textContent = content.verificationTitle;
    const body = document.createElement("p");
    body.className = "structure-section-body";
    body.textContent = content.verificationBody;
    const list = document.createElement("ul");
    list.className = "structure-rule-list";
    (content.verificationItems || []).forEach((itemText) => {
        const item = document.createElement("li");
        item.textContent = itemText;
        list.appendChild(item);
    });

    section.append(title, body, list);
    return section;
}

function buildChannelCardFromDefinition(definition) {
    const channelName = String(definition.name || "");
    const fields = Array.isArray(definition.config_fields)
        ? definition.config_fields
        : [];
    return buildChannelCard({
        label: channelLabel(channelName),
        owner: channelConfig(channelName).enabled
            ? i18n.t("channels.enabled")
            : i18n.t("channels.disabled"),
        route: `/api/channels/config:${channelName}`,
        purpose: currentText().descriptions[channelName] || String(definition.description || ""),
        fields: fields.map((field) => String(field.name || "")).filter(Boolean),
        channelName,
    });
}

function buildEditableChannelCard(definition) {
    const channelName = String(definition.name || "");
    const config = channelConfig(channelName);
    const article = document.createElement("details");
    article.className = "structure-card channels-config-card";
    article.open = Boolean(state.messages[channelName] || state.smokeResults[channelName]);

    const summary = document.createElement("summary");
    summary.className = "channels-config-summary";

    const header = document.createElement("div");
    header.className = "structure-card-header";
    const title = document.createElement("h3");
    title.textContent = channelLabel(channelName);
    const owner = document.createElement("span");
    owner.className = "structure-owner";
    owner.textContent = channelConfig(channelName).enabled
        ? i18n.t("channels.enabled")
        : i18n.t("channels.disabled");
    header.append(title, owner);

    const route = document.createElement("code");
    route.className = "structure-route";
    route.textContent = `/api/channels/config:${channelName}`;

    const purpose = document.createElement("p");
    purpose.textContent = currentText().descriptions[channelName] || i18n.t("channels.plannedPurpose");

    summary.append(header, route, purpose);

    const body = document.createElement("div");
    body.className = "channels-config-body";

    const form = document.createElement("form");
    form.dataset.channel = channelName;
    form.autocomplete = "off";

    const enabledField = buildFieldRow({
        fieldName: "enabled",
        configValue: String(Boolean(config.enabled)),
        fieldType: "checkbox",
        label: i18n.t("channels.fieldEnabled"),
        isSecret: false,
        isTextArea: false,
    });
    const enabledInput = enabledField.querySelector("input");
    if (enabledInput) {
        enabledInput.checked = Boolean(config.enabled);
    }
    form.appendChild(enabledField);

    const fieldList = collectConfigFieldDefinitions(channelName, definition);
    fieldList.forEach((fieldMeta) => {
        const fieldName = fieldMeta.name;
        if (!fieldName || fieldName === "enabled") {
            return;
        }
        if (fieldName === "allow_from") {
            const row = buildFieldRow({
                fieldName,
                configValue: allowFromText(config[fieldName]),
                fieldType: "textarea",
                label: i18n.t("channels.fieldAllowFrom"),
                isSecret: false,
                isTextArea: true,
                placeholder: i18n.t("channels.fieldAllowFromPlaceholder"),
            });
            form.appendChild(row);
            return;
        }
        if (fieldName === "stage_session_name") {
            const row = buildFieldRow({
                fieldName,
                label: fieldLabel(fieldName),
                configValue: String(config[fieldName] || ""),
                fieldType: "text",
                isSecret: false,
                isTextArea: false,
                placeholder: defaultSessionName(),
                listId: sessionDatalistId(channelName, "stage"),
            });
            form.appendChild(row);
            return;
        }
        const isSecret = isSecretField(fieldMeta);
        const isBoolean = isBooleanField(fieldMeta);
        const value = String(config[fieldName] || "");
        const row = buildFieldRow({
            fieldName,
            label: fieldLabel(fieldName),
            configValue: isSecret ? "" : value,
            fieldType: isBoolean ? "checkbox" : isSecret ? "password" : "text",
            isSecret,
            isTextArea: false,
            placeholder: isSecret ? secretFieldPlaceholder(fieldName, config) : "",
        });
        const input = row.querySelector("input");
        if (input) {
            if (isSecret && value) {
                input.value = "";
            }
            if (isBoolean) {
                input.checked = Boolean(config[fieldName]);
            }
        }
        form.appendChild(row);
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        void saveChannelConfig(form, channelName);
    });

    const controls = document.createElement("div");
    controls.className = "shell-form-actions";

    const saveButton = document.createElement("button");
    saveButton.type = "submit";
    saveButton.textContent = i18n.t("channels.saveChanges");
    saveButton.disabled = state.saving || state.smokeInFlight;
    saveButton.addEventListener("click", (event) => {
        event.preventDefault();
        void saveChannelConfig(form, channelName);
    });

    const reloadButton = document.createElement("button");
    reloadButton.type = "button";
    reloadButton.textContent = i18n.t("channels.reload");
    reloadButton.disabled = state.saving || state.smokeInFlight;
    reloadButton.addEventListener("click", () => {
        void loadChannels();
    });

    const smokeButton = document.createElement("button");
    smokeButton.type = "button";
    smokeButton.textContent = i18n.t("channels.smokeTest");
    smokeButton.disabled = state.saving || state.smokeInFlight;
    smokeButton.addEventListener("click", () => {
        void runSmokeTest(channelName);
    });

    controls.append(saveButton, reloadButton, smokeButton);

    const message = buildFeedbackMessage(channelName);
    const checks = buildSmokeChecks(channelName);
    const hints = buildChannelHints(channelName);
    const localTest = buildLocalTestControls(channelName, config);

    body.append(form, hints, controls, localTest, message, checks);
    article.append(summary, body);
    return article;
}

function collectConfigFieldDefinitions(channelName, definition) {
    const fallback = FALLBACK_FIELDS[channelName] || [];
    const configured = Array.isArray(definition.config_fields)
        ? definition.config_fields.map(normalizeFieldMeta)
        : [];
    const configuredByName = new Set(
        configured
            .map((item) => item.name)
            .filter(Boolean),
    );
    const fields = [
        ...configured,
        ...fallback.filter((field) => !configuredByName.has(field.name)),
    ];

    const ordered = [];
    const seen = new Set();
    fields.forEach((field) => {
        if (!field.name) {
            return;
        }
        const normalized = String(field.name).trim().toLowerCase();
        if (seen.has(normalized)) {
            return;
        }
        seen.add(normalized);
        ordered.push({ ...field, name: normalized });
    });
    return ordered;
}

function normalizeFieldMeta(field) {
    if (!field) {
        return { name: "", kind: "", isSecret: false };
    }
    if (typeof field === "string") {
        return { name: String(field).trim().toLowerCase(), kind: "", isSecret: false };
    }
    return {
        name: String(field.name || "").trim().toLowerCase(),
        kind: String(field.kind || field.type || "").trim().toLowerCase(),
        isSecret: Boolean(field.secret || field.sensitive),
    };
}

function isSecretField(fieldMeta) {
    if (!fieldMeta || !fieldMeta.name) {
        return false;
    }
    if (fieldMeta.isSecret) {
        return true;
    }
    const name = fieldMeta.name.toLowerCase();
    return name.startsWith("webhook_")
        || name.includes("token")
        || name.includes("secret")
        || name.includes("key")
        || name.includes("password");
}

function isBooleanField(fieldMeta) {
    if (!fieldMeta || !fieldMeta.name) {
        return false;
    }
    const kind = String(fieldMeta.kind || "").trim().toLowerCase();
    return kind === "bool" || kind === "boolean" || kind.endsWith(".bool");
}

function fieldLabel(fieldName) {
    const key = FIELD_LABEL_KEYS[fieldName];
    if (key) {
        return i18n.t(key);
    }
    const spaced = fieldName.replace(/_/g, " ");
    return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function allowFromText(value) {
    if (Array.isArray(value)) {
        return value
            .map((item) => String(item || "").trim())
            .filter(Boolean)
            .join("\n");
    }
    return String(value || "");
}

function secretFieldPlaceholder(fieldName, config) {
    if (Boolean(config[`${fieldName}_configured`])) {
        return i18n.t("channels.secretConfigured");
    }
    return i18n.t("channels.secretNotConfigured");
}

function buildFieldRow({
    fieldName,
    label,
    configValue,
    fieldType,
    isSecret,
    isTextArea,
    placeholder,
    listId,
}) {
    const field = document.createElement("label");
    field.className = "channels-field-row";

    const title = document.createElement("span");
    title.textContent = label;
    field.appendChild(title);

    let control;
    if (isTextArea) {
        control = document.createElement("textarea");
        control.value = configValue;
        control.rows = 4;
    } else if (fieldType === "checkbox") {
        control = document.createElement("input");
        control.type = "checkbox";
        control.checked = configValue === "true";
    } else {
        control = document.createElement("input");
        control.type = fieldType || "text";
        if (!isSecret) {
            control.value = configValue;
        }
    }
    control.dataset.channelField = fieldName;
    if (isTextArea || isSecret) {
        control.setAttribute("placeholder", placeholder || "");
    } else if (placeholder) {
        control.setAttribute("placeholder", placeholder);
    }
    if (!isTextArea && !isSecret && control.type !== "checkbox") {
        control.autocomplete = "off";
    }
    if (listId && control.type !== "checkbox") {
        control.setAttribute("list", listId);
    }
    field.appendChild(control);
    if (listId) {
        field.appendChild(buildSessionDatalist(listId));
    }
    return field;
}

function sessionDatalistId(channelName, suffix) {
    return `channels-session-options-${channelName}-${suffix}`;
}

function buildSessionDatalist(listId) {
    const datalist = document.createElement("datalist");
    datalist.id = listId;
    sessionNames().forEach((name) => {
        const option = document.createElement("option");
        option.value = name;
        datalist.appendChild(option);
    });
    return datalist;
}

function sessionNames() {
    return state.sessions
        .map((session) => String(session?.name || "").trim())
        .filter(Boolean);
}

function buildFeedbackMessage(channelName) {
    const block = document.createElement("p");
    block.className = "channels-field-list";
    const message = state.messages[channelName];
    if (message) {
        block.textContent = message;
        return block;
    }
    const smokeResult = state.smokeResults[channelName];
    if (!smokeResult) {
        block.textContent = "";
        return block;
    }
    const details = Array.isArray(smokeResult.checks)
        ? smokeResult.checks
            .map((check) => `${check.name || ""}: ${check.ok ? i18n.t("channels.ok") : i18n.t("channels.fail")} ${check.message || ""}`.trim())
            .join(" | ")
        : "";
    block.textContent = `${smokeResult.ok ? i18n.t("channels.smokeOk") : i18n.t("channels.smokeFailed")}: ${smokeResult.status || ""} ${details}`.trim();
    return block;
}

function buildSmokeChecks(channelName) {
    const smokeResult = state.smokeResults[channelName];
    const list = document.createElement("div");
    list.className = "channels-field-list";
    if (!smokeResult || !Array.isArray(smokeResult.checks) || smokeResult.checks.length === 0) {
        return list;
    }
    smokeResult.checks.forEach((check) => {
        const item = document.createElement("p");
        item.textContent = `${check.name || i18n.t("channels.unknown")}: ${check.ok ? i18n.t("channels.ok") : i18n.t("channels.fail")} ${check.message || ""}`.trim();
        list.appendChild(item);
    });
    return list;
}

function buildChannelHints(channelName) {
    const hints = currentText().channelHints?.[channelName] || [];
    const block = document.createElement("div");
    block.className = "channels-field-list";
    if (!Array.isArray(hints) || hints.length === 0) {
        return block;
    }
    hints.forEach((hint) => {
        const item = document.createElement("p");
        item.textContent = hint;
        block.appendChild(item);
    });
    return block;
}

function buildLocalTestControls(channelName, config) {
    const block = document.createElement("section");
    block.className = "channels-local-test";
    block.dataset.localTestChannel = channelName;

    const title = document.createElement("h4");
    title.textContent = i18n.t("channels.localTestTitle");
    const body = document.createElement("p");
    body.className = "channels-field-list";
    body.textContent = i18n.t("channels.localTestHelp");

    const grid = document.createElement("div");
    grid.className = "model-profile-field-grid";
    grid.append(
        buildLocalTestField("sender_id", i18n.t("channels.localSender"), defaultSenderId(config)),
        buildLocalTestField("chat_id", i18n.t("channels.localChat"), defaultChatId(channelName, config)),
        buildLocalTestField(
            "session_name",
            i18n.t("channels.localSession"),
            defaultStageSession(config),
            sessionDatalistId(channelName, "local-test"),
        ),
        buildLocalTestField("text", i18n.t("channels.localText"), "ping"),
    );

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = i18n.t("channels.localTestRun");
    button.disabled = state.saving || state.smokeInFlight;
    button.addEventListener("click", () => {
        void runLocalE2ETest(block, channelName);
    });

    block.append(title, body, grid, button);
    return block;
}

function buildLocalTestField(fieldName, labelText, value, listId = "") {
    const label = document.createElement("label");
    label.className = "channels-field-row";
    const title = document.createElement("span");
    title.textContent = labelText;
    const input = document.createElement("input");
    input.type = "text";
    input.autocomplete = "off";
    input.value = String(value || "");
    input.dataset.localTestField = fieldName;
    if (listId) {
        input.setAttribute("list", listId);
        label.append(title, input, buildSessionDatalist(listId));
        return label;
    }
    label.append(title, input);
    return label;
}

function defaultSenderId(config) {
    const allowList = Array.isArray(config.allow_from)
        ? config.allow_from.map((item) => String(item || "").trim()).filter(Boolean)
        : [];
    const firstAllowed = allowList.find((item) => item && item !== "*");
    return firstAllowed || "local-user";
}

function defaultChatId(channelName, config) {
    if (channelName === "discord" && config.channel_id) {
        return String(config.channel_id || "");
    }
    return defaultSenderId(config);
}

function defaultStageSession(config) {
    return String(config.stage_session_name || "default").trim() || "default";
}

function defaultSessionName() {
    return sessionNames()[0] || "default";
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
    grid.replaceChildren(...cards.map((card) => card));

    section.append(title, body, grid);
    return section;
}

function buildChannelCard(card) {
    const article = document.createElement("details");
    article.className = "structure-card channels-config-card";

    const summary = document.createElement("summary");
    summary.className = "channels-config-summary";
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

    summary.append(header, route, purpose);

    const body = document.createElement("div");
    body.className = "channels-config-body";
    const status = state.messages[card.channelName] || "";
    if (status) {
        const text = document.createElement("p");
        text.className = "channels-field-list";
        text.textContent = status;
        body.append(fields, text);
        article.append(summary, body);
        return article;
    }

    body.append(fields);
    article.append(summary, body);
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

async function saveChannelConfig(form, channelName) {
    if (state.saving || state.smokeInFlight) {
        return;
    }
    const updates = readFormValues(form);
    const nextConfig = {
        ...(state.config && typeof state.config === "object" ? state.config : {}),
    };
    nextConfig[channelName] = {
        ...channelConfig(channelName),
        ...updates,
    };
    state.saving = true;
    state.messages[channelName] = i18n.t("channels.saving");
    renderAll();
    try {
        await requestJson("/api/channels/config", {
            method: "PUT",
            body: JSON.stringify(nextConfig),
        });
        await loadChannels();
        state.messages[channelName] = i18n.t("channels.saved");
    } catch (error) {
        state.messages[channelName] = `${i18n.t("channels.saveFailed")}: ${error.message || String(error)}`;
    } finally {
        state.saving = false;
        renderAll();
    }
}

function readFormValues(form) {
    const result = {};
    const inputs = Array.from(form.querySelectorAll("[data-channel-field]"));
    inputs.forEach((input) => {
        if (!input.dataset.channelField) {
            return;
        }
        const fieldName = input.dataset.channelField;
        if (input.type === "checkbox") {
            result[fieldName] = Boolean(input.checked);
            return;
        }
        if (fieldName === "allow_from") {
            result[fieldName] = String(input.value || "")
                .split(/\r?\n|,/)
                .map((item) => item.trim())
                .filter(Boolean);
            return;
        }
        if (input.type === "password") {
            result[fieldName] = String(input.value || "").trim();
            return;
        }
        result[fieldName] = String(input.value || "").trim();
    });
    return result;
}

async function runSmokeTest(channelName) {
    if (state.saving || state.smokeInFlight) {
        return;
    }
    state.smokeInFlight = true;
    state.messages[channelName] = i18n.t("channels.smokeRunning");
    state.smokeResults[channelName] = null;
    renderAll();
    try {
        const result = await requestJson(`/api/channels/${encodeURIComponent(channelName)}/smoke`, {
            method: "POST",
        });
        state.smokeResults[channelName] = result;
        state.messages[channelName] = result.ok
            ? i18n.t("channels.smokeStarted")
            : i18n.t("channels.smokeFailed");
    } catch (error) {
        state.smokeResults[channelName] = null;
        state.messages[channelName] = `${i18n.t("channels.smokeFailed")}: ${error.message || String(error)}`;
    } finally {
        state.smokeInFlight = false;
        renderAll();
    }
}

async function runLocalE2ETest(block, channelName) {
    if (state.saving || state.smokeInFlight) {
        return;
    }
    const payload = readLocalTestValues(block);
    state.smokeInFlight = true;
    state.messages[channelName] = i18n.t("channels.localTestRunning");
    renderAll();
    try {
        const result = await requestJson(
            `/api/channels/${encodeURIComponent(channelName)}/local-test-message`,
            {
                method: "POST",
                body: JSON.stringify(payload),
            },
        );
        state.messages[channelName] = i18n.t("channels.localTestAccepted", {
            session: result.session_name || payload.session_name || i18n.t("channels.none"),
        });
    } catch (error) {
        state.messages[channelName] = `${i18n.t("channels.localTestFailed")}: ${error.message || String(error)}`;
    } finally {
        state.smokeInFlight = false;
        renderAll();
    }
}

function readLocalTestValues(block) {
    const payload = {};
    const inputs = Array.from(block.querySelectorAll("[data-local-test-field]"));
    inputs.forEach((input) => {
        const fieldName = input.dataset.localTestField;
        if (!fieldName) {
            return;
        }
        payload[fieldName] = String(input.value || "").trim();
    });
    return payload;
}

function plannedChannelCard(channel) {
    return buildChannelCard({
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
    });
}

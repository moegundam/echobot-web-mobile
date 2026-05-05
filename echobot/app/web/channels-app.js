import { initShellI18n } from "./shell-i18n.js?v=session-centered-2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

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
        { name: "webhook_url", kind: "text" },
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
            discord: "Discord webhook bridge and outbound webhook delivery. Direct Discord bot events are still a later adapter.",
            qq: "QQ official bot direct-message channel.",
        },
        channelHints: {
            telegram: [
                "Inbound uses Bot API polling. Run only one EchoBot poller for the same bot token.",
                "Keep drop pending updates enabled for clean smoke tests; disable it only when you intentionally want queued Telegram messages.",
                "Use the local E2E test to send a controlled inbound message through EchoBot without waiting for a real platform event.",
            ],
            discord: [
                "Inbound bridge endpoint: POST /api/channels/discord/webhook",
                "Required header: X-EchoBot-Discord-Secret",
                "Request JSON includes channel_id, user_id, text, and optional session_name.",
                "Outbound replies use webhook_url when configured.",
                "Use the local E2E test for session routing and Stage mirroring before wiring native bot events.",
            ],
        },
    },
    "zh-Hant": {
        builtInTitle: "目前可用 runtime channels",
        builtInBody: "Telegram 與 Discord 在此頁可編輯並可做 smoke test；其他 channel 目前仍維持唯讀。",
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
            discord: "Discord webhook bridge 與 outbound webhook 發送；原生 Discord bot events adapter 仍是後續項目。",
            qq: "QQ 官方 bot direct-message channel。",
        },
        channelHints: {
            telegram: [
                "Inbound 使用 Bot API polling；同一個 bot token 同時間只能跑一個 EchoBot poller。",
                "乾淨 smoke test 建議維持啟動時丟棄 pending updates；只有刻意要吃 Telegram 佇列訊息時才關閉。",
                "可先用本機 E2E 測試送一則受控 inbound message，不必等待真實平台事件。",
            ],
            discord: [
                "Inbound bridge endpoint：POST /api/channels/discord/webhook",
                "必要 header：X-EchoBot-Discord-Secret",
                "Request JSON 包含 channel_id、user_id、text，可選 session_name。",
                "Outbound 回覆在設定 webhook_url 後會透過 Discord webhook 發送。",
                "接原生 bot events 前，先用本機 E2E 測試驗證 session routing 與 Stage 同步。",
            ],
        },
    },
    "zh-Hans": {
        builtInTitle: "当前可用 runtime channels",
        builtInBody: "Telegram 与 Discord 在此页可编辑并可做 smoke test；其他 channel 目前仍保持只读。",
        plannedTitle: "规划中的通讯平台整合",
        plannedBody: "这些 gateway 应先在此页建立设置边界，再接 runtime adapter。",
        rulesTitle: "整合规则",
        rulesBody: "公开通讯平台要和 Open WebUI 分开。Open WebUI 是操作员工作台；channels 是公开或半公开 gateway。",
        rules: [
            "每个新平台先在此页补状态、设置字段与 smoke-test checklist。",
            "Bot token 与 secrets 放 repo 外；UI 必须遮罩，不回显明文 token。",
            "外部用户流量默认 chat-only，等 approval gate 完成后才开工具型 Agent。",
            "接收 inbound message 前必须验证 webhook 签章或 polling 身份。",
        ],
        descriptions: {
            console: "本机 console output channel，用于 smoke test。",
            telegram: "Telegram bot polling channel。",
            discord: "Discord webhook bridge 与 outbound webhook 发送；原生 Discord bot events adapter 仍是后续项目。",
            qq: "QQ 官方 bot direct-message channel。",
        },
        channelHints: {
            telegram: [
                "Inbound 使用 Bot API polling；同一个 bot token 同时间只能跑一个 EchoBot poller。",
                "干净 smoke test 建议维持启动时丢弃 pending updates；只有刻意要吃 Telegram 队列消息时才关闭。",
                "可先用本机 E2E 测试发送一则受控 inbound message，不必等待真实平台事件。",
            ],
            discord: [
                "Inbound bridge endpoint：POST /api/channels/discord/webhook",
                "必要 header：X-EchoBot-Discord-Secret",
                "Request JSON 包含 channel_id、user_id、text，可选 session_name。",
                "Outbound 回复在设置 webhook_url 后会通过 Discord webhook 发送。",
                "接原生 bot events 前，先用本机 E2E 测试验证 session routing 与 Stage 同步。",
            ],
        },
    },
};

const state = {
    definitions: [],
    config: {},
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
        buildChannelSection(
            builtInText.plannedTitle,
            builtInText.plannedBody,
            PLANNED_CHANNELS.map(plannedChannelCard),
        ),
        buildRuleSection(builtInText),
    );
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
    const article = document.createElement("article");
    article.className = "structure-card";

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

    article.append(header, route, purpose, form, hints, controls, localTest, message, checks);
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
    return name.includes("token") || name.includes("secret") || name.includes("key") || name.includes("password");
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
    }
    if (!isTextArea && !isSecret && control.type !== "checkbox") {
        control.autocomplete = "off";
    }
    field.appendChild(control);
    return field;
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
        buildLocalTestField("session_name", i18n.t("channels.localSession"), defaultStageSession(config)),
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

function buildLocalTestField(fieldName, labelText, value) {
    const label = document.createElement("label");
    label.className = "channels-field-row";
    const title = document.createElement("span");
    title.textContent = labelText;
    const input = document.createElement("input");
    input.type = "text";
    input.autocomplete = "off";
    input.value = String(value || "");
    input.dataset.localTestField = fieldName;
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

    const status = state.messages[card.channelName] || "";
    if (status) {
        const text = document.createElement("p");
        text.className = "channels-field-list";
        text.textContent = status;
        article.append(header, route, purpose, fields, text);
        return article;
    }

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

async function requestJson(url, options = {}) {
    const headers = {
        Accept: "application/json",
    };
    const requestInit = { ...options };
    const explicitContentType = requestInit.headers
        ? (requestInit.headers["Content-Type"] || requestInit.headers["content-type"])
        : null;
    if (requestInit.body && !explicitContentType) {
        headers["Content-Type"] = "application/json";
    }
    requestInit.headers = {
        ...headers,
        ...(requestInit.headers || {}),
    };

    const response = await fetch(url, requestInit);
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

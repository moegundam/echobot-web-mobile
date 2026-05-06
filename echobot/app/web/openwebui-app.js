import { initShellI18n } from "./shell-i18n.js?v=language-menu-1";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

const bridgeContent = {
    en: {
        sections: [
            {
                title: "What this bridge is",
                body: "Open WebUI stays the operator workbench. EchoBot exposes only a narrow tool interface for Stage and session workflows.",
                items: [
                    "Connect Open WebUI directly to a private LiteLLM, Ollama, or another OpenAI-compatible provider for model usage.",
                    "Register EchoBot as an OpenAPI tool server with the tool spec URL shown above.",
                    "Use the bridge bearer token from `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN`; this page never displays the token value.",
                    "Keep Telegram, LINE, Discord, WhatsApp, and similar public gateways in `/admin/channels`.",
                ],
            },
            {
                title: "Available tool endpoints",
                body: "The bridge spec intentionally exposes fewer endpoints than the full EchoBot API.",
                items: [
                    "`GET /api/openwebui/sessions` lists EchoBot sessions visible to the selected bridge target.",
                    "`POST /api/openwebui/stage/events` sends final text to Stage subtitles and TTS.",
                    "`POST /api/openwebui/chat` sends an operator message into an EchoBot session.",
                    "`GET /api/openwebui/tools/openapi.json` is the OpenAPI tool spec for Open WebUI.",
                ],
            },
            {
                title: "Safe default behavior",
                body: "The bridge is designed as an operator interface, not a full remote-control surface.",
                items: [
                    "Chat defaults to `chat_only` so Open WebUI does not trigger file, shell, deploy, or network-capable Agent tools.",
                    "`auto` and `force_agent` are blocked unless `ECHOBOT_OPENWEBUI_OPERATOR_AGENT_ENABLED=true` is set deliberately.",
                    "When trusted-user mode is enabled, set `target_user_id` or `ECHOBOT_OPENWEBUI_BRIDGE_USER_ID` so Stage/session scope matches the viewer.",
                    "The public full `/openapi.json` remains separate and should not be imported into Open WebUI as an unrestricted tool server.",
                ],
            },
            {
                title: "Expected setup result",
                body: "After Open WebUI is configured later, the first smoke test should not require any external chat platform.",
                items: [
                    "Open Stage with `/stage?session_name=demo`.",
                    "From Open WebUI, call the Stage tool with `session_name=demo` and short text.",
                    "Stage should update the subtitle for the same target user and session.",
                    "Then call the chat tool and confirm the EchoBot session history changes under the selected target user.",
                ],
            },
            {
                title: "Local bridge verification",
                body: "Use the repo smoke script before registering the tool server in Open WebUI.",
                items: [
                    "Run `python scripts/openwebui_bridge_smoke.py --base-url http://127.0.0.1:8001 --session-name demo` with `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN` set.",
                    "The script checks status, the narrow tool spec, session listing, and Stage event publishing.",
                    "Use `--chat-prompt` only when the selected model provider is ready to answer.",
                ],
            },
            {
                title: "Stable local entrypoint",
                body: "The repeatable local service path is managed by `scripts/echobot_entrypoint.py`; it keeps EchoBot and the GB10 reverse bridge from depending on one-off terminal commands.",
                items: [
                    "`python scripts/echobot_entrypoint.py doctor` checks local tools, runtime files, SSH, Cloudflare CLI presence, and reachable health endpoints.",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local status` shows the launchd app and GB10 reverse-tunnel status.",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local smoke-openwebui --target local --session-name demo` verifies the local bridge.",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local smoke-openwebui --target gb10 --session-name demo` verifies the bridge from the Open WebUI host side.",
                ],
            },
        ],
    },
    "zh-Hant": {
        sections: [
            {
                title: "這個 Bridge 是什麼",
                body: "Open WebUI 保持操作員工作台定位。EchoBot 只暴露受控工具介面，用於 Stage 與 session 工作流。",
                items: [
                    "Open WebUI 的模型使用直接接私有 LiteLLM、Ollama 或其他 OpenAI-compatible provider。",
                    "在 Open WebUI 把 EchoBot 註冊成 OpenAPI tool server，tool spec URL 使用上方顯示的路徑。",
                    "Bearer token 使用 `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN`，本頁只顯示是否已設定，不顯示 token 值。",
                    "Telegram、LINE、Discord、WhatsApp 等公開通訊 gateway 保留在 `/admin/channels`。",
                ],
            },
            {
                title: "可用工具端點",
                body: "Bridge spec 只暴露小範圍端點，不把整個 EchoBot API 開給 Open WebUI。",
                items: [
                    "`GET /api/openwebui/sessions` 列出 bridge target 可見的 EchoBot sessions。",
                    "`POST /api/openwebui/stage/events` 把最終文字送到 Stage 字幕與 TTS。",
                    "`POST /api/openwebui/chat` 以操作員身份送訊息到 EchoBot session。",
                    "`GET /api/openwebui/tools/openapi.json` 是給 Open WebUI 匯入的 OpenAPI tool spec。",
                ],
            },
            {
                title: "安全預設行為",
                body: "Bridge 定位是操作員入口，不是完整遠端控制介面。",
                items: [
                    "Chat 預設 `chat_only`，避免 Open WebUI 觸發檔案、shell、部署或網路型 Agent tools。",
                    "`auto` 與 `force_agent` 預設封鎖；只有明確設定 `ECHOBOT_OPENWEBUI_OPERATOR_AGENT_ENABLED=true` 才會開啟。",
                    "啟用 trusted-user mode 時，設定 `target_user_id` 或 `ECHOBOT_OPENWEBUI_BRIDGE_USER_ID`，讓 Stage/session scope 對到觀看者。",
                    "全站 `/openapi.json` 仍然獨立，不應匯入 Open WebUI 當成不受限工具伺服器。",
                ],
            },
            {
                title: "預期設定成果",
                body: "之後真的接 Open WebUI 時，第一個 smoke test 不需要任何外部通訊平台。",
                items: [
                    "用 `/stage?session_name=demo` 開啟 Stage。",
                    "從 Open WebUI 呼叫 Stage tool，帶入 `session_name=demo` 與短文字。",
                    "Stage 應該在同一 target user 與同一 session 下更新字幕。",
                    "再呼叫 chat tool，確認 EchoBot session history 寫入選定的 target user namespace。",
                ],
            },
            {
                title: "本機 Bridge 驗證",
                body: "在 Open WebUI 註冊 tool server 前，先用 repo smoke script 驗證 EchoBot 端。",
                items: [
                    "設定 `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN` 後執行 `python scripts/openwebui_bridge_smoke.py --base-url http://127.0.0.1:8001 --session-name demo`。",
                    "腳本會檢查 status、窄 tool spec、session list 與 Stage event 發布。",
                    "只有在模型 provider 已可回覆時，才加 `--chat-prompt` 做 chat 工具驗證。",
                ],
            },
            {
                title: "穩定本機入口",
                body: "可重跑的本機服務入口由 `scripts/echobot_entrypoint.py` 管理，避免 EchoBot 與 GB10 reverse bridge 依賴一次性的 terminal 指令。",
                items: [
                    "`python scripts/echobot_entrypoint.py doctor` 檢查本機工具、runtime 檔案、SSH、Cloudflare CLI 是否存在，以及 health endpoint 是否可達。",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local status` 顯示 launchd app 與 GB10 reverse tunnel 狀態。",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local smoke-openwebui --target local --session-name demo` 驗證本機 bridge。",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local smoke-openwebui --target gb10 --session-name demo` 從 Open WebUI 主機視角驗證 bridge。",
                ],
            },
        ],
    },
    "zh-Hans": {
        sections: [
            {
                title: "这个 Bridge 是什么",
                body: "Open WebUI 保持操作员工作台定位。EchoBot 只暴露受控工具接口，用于 Stage 与 session 工作流。",
                items: [
                    "Open WebUI 的模型使用直接接私有 LiteLLM、Ollama 或其他 OpenAI-compatible provider。",
                    "在 Open WebUI 把 EchoBot 注册成 OpenAPI tool server，tool spec URL 使用上方显示的路径。",
                    "Bearer token 使用 `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN`，本页只显示是否已设置，不显示 token 值。",
                    "Telegram、LINE、Discord、WhatsApp 等公开通讯 gateway 保留在 `/admin/channels`。",
                ],
            },
            {
                title: "可用工具端点",
                body: "Bridge spec 只暴露小范围端点，不把整个 EchoBot API 开给 Open WebUI。",
                items: [
                    "`GET /api/openwebui/sessions` 列出 bridge target 可见的 EchoBot sessions。",
                    "`POST /api/openwebui/stage/events` 把最终文字送到 Stage 字幕与 TTS。",
                    "`POST /api/openwebui/chat` 以操作员身份发送消息到 EchoBot session。",
                    "`GET /api/openwebui/tools/openapi.json` 是给 Open WebUI 导入的 OpenAPI tool spec。",
                ],
            },
            {
                title: "安全默认行为",
                body: "Bridge 定位是操作员入口，不是完整远端控制界面。",
                items: [
                    "Chat 默认 `chat_only`，避免 Open WebUI 触发文件、shell、部署或网络型 Agent tools。",
                    "`auto` 与 `force_agent` 默认封锁；只有明确设置 `ECHOBOT_OPENWEBUI_OPERATOR_AGENT_ENABLED=true` 才会开启。",
                    "启用 trusted-user mode 时，设置 `target_user_id` 或 `ECHOBOT_OPENWEBUI_BRIDGE_USER_ID`，让 Stage/session scope 对到观看者。",
                    "全站 `/openapi.json` 仍然独立，不应导入 Open WebUI 当成不受限工具服务器。",
                ],
            },
            {
                title: "预期设置结果",
                body: "之后真的接 Open WebUI 时，第一个 smoke test 不需要任何外部通讯平台。",
                items: [
                    "用 `/stage?session_name=demo` 打开 Stage。",
                    "从 Open WebUI 调用 Stage tool，带入 `session_name=demo` 与短文字。",
                    "Stage 应该在同一 target user 与同一 session 下更新字幕。",
                    "再调用 chat tool，确认 EchoBot session history 写入选定的 target user namespace。",
                ],
            },
            {
                title: "本机 Bridge 验证",
                body: "在 Open WebUI 注册 tool server 前，先用 repo smoke script 验证 EchoBot 端。",
                items: [
                    "设置 `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN` 后执行 `python scripts/openwebui_bridge_smoke.py --base-url http://127.0.0.1:8001 --session-name demo`。",
                    "脚本会检查 status、窄 tool spec、session list 与 Stage event 发布。",
                    "只有在模型 provider 已可回复时，才加 `--chat-prompt` 做 chat 工具验证。",
                ],
            },
            {
                title: "稳定本机入口",
                body: "可重跑的本机服务入口由 `scripts/echobot_entrypoint.py` 管理，避免 EchoBot 与 GB10 reverse bridge 依赖一次性的 terminal 指令。",
                items: [
                    "`python scripts/echobot_entrypoint.py doctor` 检查本机工具、runtime 文件、SSH、Cloudflare CLI 是否存在，以及 health endpoint 是否可达。",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local status` 显示 launchd app 与 GB10 reverse tunnel 状态。",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local smoke-openwebui --target local --session-name demo` 验证本机 bridge。",
                    "`python scripts/echobot_entrypoint.py --env-file .env.launchd.local smoke-openwebui --target gb10 --session-name demo` 从 Open WebUI 主机视角验证 bridge。",
                ],
            },
        ],
    },
};

const statusGrid = document.getElementById("openwebui-status-grid");
const contentRoot = document.getElementById("openwebui-content");
let statusPayload = null;
let statusError = "";

const i18n = initShellI18n({
    onChange: () => {
        renderAll();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
initShellSessionLinks();

renderAll();
loadBridgeStatus();

function renderAll() {
    renderStatus();
    renderContent();
}

async function loadBridgeStatus() {
    try {
        const response = await fetch("/api/openwebui/status", {
            headers: {
                "Accept": "application/json",
            },
        });
        if (!response.ok) {
            throw await responseToError(response);
        }
        statusPayload = await response.json();
        statusError = "";
    } catch (error) {
        statusPayload = null;
        statusError = error.message || String(error);
    }
    renderStatus();
}

function renderStatus() {
    if (!statusGrid) {
        return;
    }
    if (statusError) {
        statusGrid.replaceChildren(
            buildStatusCard(
                i18n.t("openwebui.statusError"),
                i18n.t("openwebui.statusErrorBody", { message: statusError }),
                "danger",
            ),
        );
        return;
    }
    if (!statusPayload) {
        statusGrid.replaceChildren(
            buildStatusCard(
                i18n.t("openwebui.statusLoading"),
                i18n.t("openwebui.statusLoadingBody"),
                "muted",
            ),
        );
        return;
    }

    const items = [
        {
            title: i18n.t("openwebui.token"),
            value: statusPayload.token_configured
                ? i18n.t("openwebui.configured")
                : i18n.t("openwebui.missing"),
            tone: statusPayload.token_configured ? "ok" : "danger",
        },
        {
            title: i18n.t("openwebui.defaultUser"),
            value: statusPayload.default_user_configured
                ? i18n.t("openwebui.configured")
                : i18n.t("openwebui.notSet"),
            tone: statusPayload.default_user_configured ? "ok" : "muted",
        },
        {
            title: i18n.t("openwebui.allowedTargets"),
            value: statusPayload.allowed_target_users_configured
                ? i18n.t("openwebui.configured")
                : i18n.t("openwebui.notSet"),
            tone: statusPayload.allowed_target_users_configured ? "ok" : "warn",
        },
        {
            title: i18n.t("openwebui.requireTargetUser"),
            value: statusPayload.require_target_user
                ? i18n.t("openwebui.required")
                : i18n.t("openwebui.optional"),
            tone: statusPayload.require_target_user ? "ok" : "warn",
        },
        {
            title: i18n.t("openwebui.agentMode"),
            value: statusPayload.operator_agent_enabled
                ? i18n.t("openwebui.enabled")
                : i18n.t("openwebui.disabled"),
            tone: statusPayload.operator_agent_enabled ? "warn" : "ok",
        },
        {
            title: i18n.t("openwebui.toolSpec"),
            value: statusPayload.tool_spec_url || "/api/openwebui/tools/openapi.json",
            tone: "mono",
        },
        {
            title: i18n.t("openwebui.stageEndpoint"),
            value: statusPayload.stage_event_url || "/api/openwebui/stage/events",
            tone: "mono",
        },
        {
            title: i18n.t("openwebui.chatEndpoint"),
            value: statusPayload.chat_url || "/api/openwebui/chat",
            tone: "mono",
        },
        {
            title: i18n.t("openwebui.sessionsEndpoint"),
            value: statusPayload.sessions_url || "/api/openwebui/sessions",
            tone: "mono",
        },
        {
            title: i18n.t("openwebui.provider"),
            value: statusPayload.model_provider_recommendation || i18n.t("openwebui.providerFallback"),
            tone: "muted",
        },
        {
            title: i18n.t("openwebui.security"),
            value: securityWarningText(statusPayload.security_warnings),
            tone: Array.isArray(statusPayload.security_warnings) && statusPayload.security_warnings.length > 0
                ? "warn"
                : "ok",
        },
    ];
    statusGrid.replaceChildren(...items.map((item) => buildStatusCard(item.title, item.value, item.tone)));
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

function renderContent() {
    if (!contentRoot) {
        return;
    }
    const content = bridgeContent[i18n.language] || bridgeContent.en;
    contentRoot.replaceChildren(
        ...content.sections.map((section, index) => buildGuideSection(section, index)),
    );
}

function securityWarningText(warnings) {
    if (!Array.isArray(warnings) || warnings.length === 0) {
        return i18n.t("openwebui.securityOk");
    }
    return warnings.join(" | ");
}

function buildGuideSection(section, index) {
    const article = document.createElement("article");
    article.className = "guide-section";

    const heading = document.createElement("h2");
    heading.textContent = `${index + 1}. ${section.title}`;

    const body = document.createElement("p");
    body.className = "guide-section-body";
    body.textContent = section.body;

    const list = document.createElement("ul");
    list.className = "guide-list";
    section.items.forEach((item) => {
        const listItem = document.createElement("li");
        listItem.textContent = item;
        list.appendChild(listItem);
    });

    article.append(heading, body, list);
    return article;
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

import { initShellI18n } from "./shell-i18n.js?v=session-centered-2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

const structureContent = {
    en: {
        sections: [
            {
                title: "Session-centered entry points",
                body: "Use the same session for all runtime pages. Admin prepares resources, Console runs session operations, and Messenger/Stage are the test entry and result view.",
                cards: [
                    {
                        label: "Stage",
                        route: "/stage?session_name=<name>",
                        owner: "Front display",
                        purpose: "Display-only output for one session: character, subtitles, TTS, and Live2D lip sync.",
                    },
                    {
                        label: "Messenger",
                        route: "/messenger?session_name=<name>",
                        owner: "Session input",
                        purpose: "Lightweight message input that publishes final assistant output to Stage.",
                    },
                    {
                        label: "Console",
                        route: "/console",
                        owner: "Operator workbench",
                        purpose: "Session-centered runtime controls: role card, model, voice, Live2D, and session-level settings.",
                    },
                    {
                        label: "Admin",
                        route: "/admin",
                        owner: "Back office",
                        purpose: "Setup hub for model/voice/live2d profiles, character binding, channels, and documentation.",
                    },
                ],
            },
            {
                title: "Console page structure",
                body: "Console stays the only live workbench in this flow.",
                cards: [
                    {
                        label: "Session panel",
                        route: "/console left side",
                        owner: "Visual runtime",
                        purpose: "Connection state, active session state, character/model profile, language, and Live2D display.",
                    },
                    {
                        label: "Control drawers",
                        route: "Console side panels",
                        owner: "Session control",
                        purpose: "Session list and character card selection for the active session.",
                    },
                    {
                        label: "Settings groups",
                        route: "Console details panels",
                        owner: "Runtime configuration",
                        purpose: "Route mode, provider switch, ASR/TTS, Live2D, CRON, and HEARTBEAT.",
                    },
                    {
                        label: "Conversation area",
                        route: "/api/chat* + /api/sessions*",
                        owner: "Active operation",
                        purpose: "Session transcript, attachments, microphone input, and send controls.",
                    },
                ],
            },
            {
                title: "Admin child pages",
                body: "Admin pages are for setup and reference. Runtime changes are made in Console context.",
                cards: [
                    {
                        label: "Site Structure",
                        route: "/admin/structure",
                        owner: "Information architecture",
                        purpose: "Route map, page boundaries, Console breakdown, and API namespace grouping.",
                    },
                    {
                        label: "Operation Guide",
                        route: "/admin/guide",
                        owner: "Guide",
                        purpose: "Session flow and operation reference.",
                    },
                    {
                        label: "Sessions",
                        route: "/admin/sessions",
                        owner: "Session maintenance",
                        purpose: "Session create, rename, delete, and handoff checks before Console operation.",
                    },
                    {
                        label: "LLM Models",
                        route: "/admin/models",
                        owner: "LLM configuration",
                        purpose: "LLM profile setup used by character binding.",
                    },
                    {
                        label: "Voice Models",
                        route: "/admin/voice-models",
                        owner: "Speech configuration",
                        purpose: "STT/TTS profile setup: voice, language, and provider status.",
                    },
                    {
                        label: "Live2D Models",
                        route: "/admin/live2d",
                        owner: "Visual configuration",
                        purpose: "Live2D catalog and visual profile selection.",
                    },
                    {
                        label: "Characters",
                        route: "/admin/characters",
                        owner: "Character setup",
                        purpose: "Bind LLM, voice, and Live2D profiles into a character.",
                    },
                    {
                        label: "Channels",
                        route: "/admin/channels",
                        owner: "Messaging gateways",
                        purpose: "Channel entry settings. Telegram/Discord are smoke-ready; LINE/WhatsApp/QQ are planned.",
                    },
                    {
                        label: "Open WebUI Bridge",
                        route: "/admin/openwebui",
                        owner: "Operator bridge",
                        purpose: "Operator tool-interface configuration and bridge status.",
                    },
                ],
            },
            {
                title: "API namespace boundaries",
                body: "The APIs are grouped so admin config and session runtime do not cross paths.",
                cards: [
                    {
                        label: "Console API",
                        route: "/api/web/*",
                        owner: "Console",
                        purpose: "Web config, runtime settings, Live2D assets, stage backgrounds, TTS, and ASR including WebSocket.",
                    },
                    {
                        label: "Conversation API",
                        route: "/api/chat*, /api/sessions*, /api/roles*, /api/attachments*",
                        owner: "Chat runtime",
                        purpose: "Messages, jobs, session storage, role cards, and file uploads/downloads.",
                    },
                    {
                        label: "Stage API",
                        route: "/api/stage/events",
                        owner: "Stage event broker",
                        purpose: "User/session-scoped stage-event publish and SSE subscribe.",
                    },
                    {
                        label: "Admin/bridge API",
                        route: "/api/character-profiles*, /api/model-profiles*, /api/llm-models, /api/voice-models, /api/live2d-models, /api/channel-integrations, /api/openwebui/*, /api/health",
                        owner: "Back office",
                        purpose: "Character binding, split model profiles, channel status, Open WebUI bridge tools, and health checks.",
                    },
                ],
            },
            {
                title: "Routing rules",
                body: "Keep these in mind for stable growth.",
                items: [
                    "Session flow: Admin setup → Console session operation → Messenger + Stage verification.",
                    "Channels are entry points, not the core control loop.",
                    "Telegram / Discord can be tested now; LINE, WhatsApp, QQ are planned.",
                    "Stage is output-only for a selected session.",
                    "Open WebUI bridge is operator tool integration, not regular chat routing.",
                ],
            },
        ],
    },
    "zh-Hant": {
        sections: [
            {
                title: "以 Session 為中心的入口",
                body: "固定用 session 走同一流程：Admin 先準備資源，Console 執行會話操作，Messenger 與 Stage 做輸入與結果驗證。",
                cards: [
                    {
                        label: "前台 Stage",
                        route: "/stage?session_name=<name>",
                        owner: "純顯示畫面",
                        purpose: "單一 session 的顯示結果面：角色、字幕、TTS 與 Live2D。",
                    },
                    {
                        label: "通訊 Messenger",
                        route: "/messenger?session_name=<name>",
                        owner: "會話輸入",
                        purpose: "輕量輸入，最終訊息可在 Stage 上同步顯示。",
                    },
                    {
                        label: "中台 Console",
                        route: "/console",
                        owner: "操作員工作台",
                        purpose: "以 session 為核心進行角色卡、模型、語音、Live2D 與運行參數切換。",
                    },
                    {
                        label: "後台 Admin",
                        route: "/admin",
                        owner: "設定中枢",
                        purpose: "模型/語音/Live2D 設定、角色綁定、通道與文件頁面入口。",
                    },
                ],
            },
            {
                title: "Console 內部結構",
                body: "Console 是該流程中的即時工作台，不在 Stage 放操作控制。",
                cards: [
                    {
                        label: "Session 面板",
                        route: "/console 左側",
                        owner: "視覺 runtime",
                        purpose: "連線狀態、session 狀態、目前角色模型、語言與 Live2D 顯示。",
                    },
                    {
                        label: "控制抽屜",
                        route: "Console side panels",
                        owner: "Session control",
                        purpose: "顯示 session 清單與目前 session 的角色卡。",
                    },
                    {
                        label: "設定群組",
                        route: "Console details panels",
                        owner: "Runtime configuration",
                        purpose: "Route mode、provider 切換、ASR/TTS、Live2D、CRON 與 HEARTBEAT。",
                    },
                    {
                        label: "對話區",
                        route: "/api/chat* + /api/sessions*",
                        owner: "即時操作",
                        purpose: "會話訊息、附件、麥克風輸入與送出控制。",
                    },
                ],
            },
            {
                title: "Admin 子頁面",
                body: "Admin 是設定與參考入口，會話運行仍在 Console 裡完成。",
                cards: [
                    {
                        label: "網站結構",
                        route: "/admin/structure",
                        owner: "資訊架構",
                        purpose: "路由地圖、頁面邊界、Console 分區與 API namespace。",
                    },
                    {
                        label: "操作說明",
                        route: "/admin/guide",
                        owner: "操作指南",
                        purpose: "Session 流程與操作參考。",
                    },
                    {
                        label: "會話管理",
                        route: "/admin/sessions",
                        owner: "Session 維運",
                        purpose: "建立、重命名、刪除及進入 Console 前的檢查。",
                    },
                    {
                        label: "LLM 模型",
                        route: "/admin/models",
                        owner: "LLM 設定",
                        purpose: "建立角色綁定所需的 LLM profile。",
                    },
                    {
                        label: "語音模型",
                        route: "/admin/voice-models",
                        owner: "語音設定",
                        purpose: "建立 STT/TTS profile：聲音、語言與提供者狀態。",
                    },
                    {
                        label: "Live2D 模型",
                        route: "/admin/live2d",
                        owner: "視覺設定",
                        purpose: "管理 Live2D catalog 與視覺 profile。",
                    },
                    {
                        label: "角色設定",
                        route: "/admin/characters",
                        owner: "角色設定",
                        purpose: "把 LLM、語音、Live2D profile 綁到角色。",
                    },
                    {
                        label: "通訊平台",
                        route: "/admin/channels",
                        owner: "Messaging gateways",
                        purpose: "通道進入點設定。Telegram/Discord 可做 smoke，LINE/WhatsApp/QQ 為規劃中。",
                    },
                    {
                        label: "Open WebUI Bridge",
                        route: "/admin/openwebui",
                        owner: "操作員 bridge",
                        purpose: "操作員工具接口（Open WebUI bridge）設定與狀態。",
                    },
                ],
            },
            {
                title: "API namespace 邊界",
                body: "按 session 流程分 admin 與對話 API，避免控制與設定耦合。",
                cards: [
                    {
                        label: "Console API",
                        route: "/api/web/*",
                        owner: "Console",
                        purpose: "Web config、runtime settings、Live2D assets、stage backgrounds、TTS、ASR 與 WebSocket。",
                    },
                    {
                        label: "Conversation API",
                        route: "/api/chat*, /api/sessions*, /api/roles*, /api/attachments*",
                        owner: "對話 runtime",
                        purpose: "訊息、jobs、session 儲存、角色卡與檔案上傳下載。",
                    },
                    {
                        label: "Stage API",
                        route: "/api/stage/events",
                        owner: "Stage event broker",
                        purpose: "以 user/session scope 做字幕與舞台狀態 publish/SSE 訂閱。",
                    },
                    {
                        label: "Admin/Bridge API",
                        route: "/api/character-profiles*, /api/model-profiles*, /api/llm-models, /api/voice-models, /api/live2d-models, /api/channel-integrations, /api/openwebui/*, /api/health",
                        owner: "後台",
                        purpose: "角色綁定、拆分 model profile、通道狀態、Open WebUI bridge tools 與健康檢查。",
                    },
                ],
            },
            {
                title: "路由增長規則",
                body: "後續擴充請維持以下順序與邊界。",
                items: [
                    "Session 流程為 Admin 設定 -> Console 會話操作 -> Messenger + Stage 驗證。",
                    "通道是入口，不是核心控台；Telegram/Discord 已可測，LINE、WhatsApp、QQ 規劃中。",
                    "Stage 只顯示指定 session 的結果。",
                    "Open WebUI Bridge 為操作員工具接線，不作為一般對話路由。",
                ],
            },
        ],
    },
    "zh-Hans": {
        sections: [
            {
                title: "以 Session 为核心的入口",
                body: "固定用同一个 session 流程：Admin 先准备资源，Console 做会话操作，Messenger 与 Stage 做输入和结果验证。",
                cards: [
                    {
                        label: "前台 Stage",
                        route: "/stage?session_name=<name>",
                        owner: "纯显示画面",
                        purpose: "单一 session 的显示结果面：角色、字幕、TTS 与 Live2D。",
                    },
                    {
                        label: "通讯 Messenger",
                        route: "/messenger?session_name=<name>",
                        owner: "会话输入",
                        purpose: "轻量输入，最终消息可在 Stage 上同步显示。",
                    },
                    {
                        label: "中台 Console",
                        route: "/console",
                        owner: "操作员工作台",
                        purpose: "以 session 为核心切换角色卡、模型、语音、Live2D 与运行参数。",
                    },
                    {
                        label: "后台 Admin",
                        route: "/admin",
                        owner: "设置中心",
                        purpose: "模型/语音/Live2D 设置、角色绑定、通道和文档页面入口。",
                    },
                ],
            },
            {
                title: "Console 页面内部结构",
                body: "Console 是实时工作台，Stage 不承载即时控制。",
                cards: [
                    {
                        label: "Session 面板",
                        route: "/console 左侧",
                        owner: "Visual runtime",
                        purpose: "连接状态、session 状态、当前角色模型、语言与 Live2D 显示。",
                    },
                    {
                        label: "控制抽屉",
                        route: "Console side panels",
                        owner: "Session control",
                        purpose: "显示 session 列表与当前 session 的角色卡。",
                    },
                    {
                        label: "设置群组",
                        route: "Console details panels",
                        owner: "Runtime configuration",
                        purpose: "Route mode、provider 切换、ASR/TTS、Live2D、CRON 与 HEARTBEAT。",
                    },
                    {
                        label: "对话区",
                        route: "/api/chat* + /api/sessions*",
                        owner: "即时操作",
                        purpose: "会话消息、附件、麦克风输入与发送控制。",
                    },
                ],
            },
            {
                title: "Admin 子页面",
                body: "Admin 是设置与参考入口，session 运行仍在 Console 内完成。",
                cards: [
                    {
                        label: "网站结构",
                        route: "/admin/structure",
                        owner: "信息架构",
                        purpose: "路由地图、页面边界、Console 分区与 API namespace。",
                    },
                    {
                        label: "操作说明",
                        route: "/admin/guide",
                        owner: "操作指南",
                        purpose: "Session 流程与操作参考。",
                    },
                    {
                        label: "会话管理",
                        route: "/admin/sessions",
                        owner: "Session 维护",
                        purpose: "创建、重命名、删除并准备进入 Console。",
                    },
                    {
                        label: "LLM 模型",
                        route: "/admin/models",
                        owner: "LLM 设置",
                        purpose: "建立角色绑定所需的 LLM profile。",
                    },
                    {
                        label: "语音模型",
                        route: "/admin/voice-models",
                        owner: "语音设置",
                        purpose: "建立 STT/TTS profile：声音、语言与提供者状态。",
                    },
                    {
                        label: "Live2D 模型",
                        route: "/admin/live2d",
                        owner: "视觉设置",
                        purpose: "管理 Live2D catalog 与视觉 profile。",
                    },
                    {
                        label: "角色设置",
                        route: "/admin/characters",
                        owner: "角色设置",
                        purpose: "将 LLM、语音、Live2D profile 绑定到角色。",
                    },
                    {
                        label: "通讯平台",
                        route: "/admin/channels",
                        owner: "Messaging gateways",
                        purpose: "通道入口设置。Telegram/Discord 可做 smoke，LINE/WhatsApp/QQ 为规划中。",
                    },
                    {
                        label: "Open WebUI Bridge",
                        route: "/admin/openwebui",
                        owner: "操作员 bridge",
                        purpose: "操作员工具接口（Open WebUI bridge）设置与状态。",
                    },
                ],
            },
            {
                title: "API namespace 边界",
                body: "按 session 流程区分 admin 与对话 API，避免控制与设置混用。",
                cards: [
                    {
                        label: "Console API",
                        route: "/api/web/*",
                        owner: "Console",
                        purpose: "Web config、runtime settings、Live2D assets、stage backgrounds、TTS、ASR 与 WebSocket。",
                    },
                    {
                        label: "Conversation API",
                        route: "/api/chat*, /api/sessions*, /api/roles*, /api/attachments*",
                        owner: "聊天 runtime",
                        purpose: "消息、jobs、session 存储、角色卡与文件上传下载。",
                    },
                    {
                        label: "Stage API",
                        route: "/api/stage/events",
                        owner: "Stage event broker",
                        purpose: "以 user/session scope 做字幕与舞台状态 publish/SSE 订阅。",
                    },
                    {
                        label: "Admin/Bridge API",
                        route: "/api/character-profiles*, /api/model-profiles*, /api/llm-models, /api/voice-models, /api/live2d-models, /api/channel-integrations, /api/openwebui/*, /api/health",
                        owner: "后台",
                        purpose: "角色绑定、拆分 model profile、通道状态、Open WebUI bridge tools 与健康检查。",
                    },
                ],
            },
            {
                title: "Route 增长规则",
                body: "后续扩展请保持以下顺序与边界。",
                items: [
                    "Session 流程固定为 Admin 设置 -> Console 会话操作 -> Messenger + Stage 验证。",
                    "通道是入口，不是核心；Telegram/Discord 已可测试，LINE、WhatsApp、QQ 规划中。",
                    "Stage 只展示指定 session 的结果。",
                    "Open WebUI Bridge 作为操作员工具接口，不作为一般对话路由。",
                ],
            },
        ],
    },
};

const contentRoot = document.getElementById("structure-content");
const i18n = initShellI18n({
    onChange: () => {
        renderStructure();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
initShellSessionLinks();

renderStructure();

function renderStructure() {
    if (!contentRoot) {
        return;
    }
    const content = structureContent[i18n.language] || structureContent.en;
    contentRoot.replaceChildren(
        ...content.sections.map((section, index) => buildSection(section, index)),
    );
}

function buildSection(section, index) {
    const article = document.createElement("article");
    article.className = "structure-section";

    const heading = document.createElement("h2");
    heading.textContent = `${index + 1}. ${section.title}`;

    const body = document.createElement("p");
    body.className = "structure-section-body";
    body.textContent = section.body;

    article.append(heading, body);

    if (Array.isArray(section.cards)) {
        const grid = document.createElement("div");
        grid.className = "structure-card-grid";
        section.cards.forEach((card) => {
            grid.appendChild(buildCard(card));
        });
        article.appendChild(grid);
    }

    if (Array.isArray(section.items)) {
        const list = document.createElement("ul");
        list.className = "structure-rule-list";
        section.items.forEach((item) => {
            const listItem = document.createElement("li");
            listItem.textContent = item;
            list.appendChild(listItem);
        });
        article.appendChild(list);
    }

    return article;
}

function buildCard(card) {
    const element = document.createElement("section");
    element.className = "structure-card";

    const header = document.createElement("div");
    header.className = "structure-card-header";

    const label = document.createElement("h3");
    label.textContent = card.label;

    const owner = document.createElement("span");
    owner.className = "structure-owner";
    owner.textContent = card.owner;

    header.append(label, owner);

    const route = document.createElement("code");
    route.className = "structure-route";
    route.textContent = card.route;

    const purpose = document.createElement("p");
    purpose.textContent = card.purpose;

    element.append(header, route, purpose);
    return element;
}

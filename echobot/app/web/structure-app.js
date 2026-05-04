import { initShellI18n } from "./shell-i18n.js?v=site-public-6";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

const structureContent = {
    en: {
        sections: [
            {
                title: "Top-level product entrances",
                body: "Use the route by the person and job. Stage is for display, Messenger is for chat, Console is for operation, and Admin is for management references.",
                cards: [
                    {
                        label: "Stage",
                        route: "/stage?session_name=<name>",
                        owner: "Front display",
                        purpose: "Character screen, subtitles, TTS playback, and Live2D lip sync for one session.",
                    },
                    {
                        label: "Messenger",
                        route: "/messenger?session_name=<name>",
                        owner: "Communication",
                        purpose: "Lightweight chat entrance that sends final assistant text to Stage.",
                    },
                    {
                        label: "Console",
                        route: "/console",
                        owner: "Operator workbench",
                        purpose: "Full runtime control for sessions, role cards, ASR, TTS, Live2D, jobs, CRON, and HEARTBEAT.",
                    },
                    {
                        label: "Admin",
                        route: "/admin",
                        owner: "Back office",
                        purpose: "Protected index for health, API docs, model profiles, Open WebUI bridge, and documentation pages.",
                    },
                ],
            },
            {
                title: "Console page structure",
                body: "Console stays as one operator workbench. Its panels are separated by responsibility, not by visual decoration.",
                cards: [
                    {
                        label: "Stage panel",
                        route: "/console left side",
                        owner: "Visual runtime",
                        purpose: "Connection state, session badge, active model profile, language/display controls, Live2D stage, and Live2D drawer.",
                    },
                    {
                        label: "Control drawers",
                        route: "Console side panels",
                        owner: "Operator setup",
                        purpose: "Session list and role card selection/editing. These should stay scoped to the current trusted user.",
                    },
                    {
                        label: "Settings groups",
                        route: "Console details panels",
                        owner: "Runtime configuration",
                        purpose: "Route mode, provider/runtime safety, ASR, TTS, stage assets, CRON, and HEARTBEAT.",
                    },
                    {
                        label: "Conversation area",
                        route: "/api/chat* + /api/sessions*",
                        owner: "Active operation",
                        purpose: "Current session transcript, agent trace, attachments, microphone input, and send controls.",
                    },
                ],
            },
            {
                title: "Admin child pages",
                body: "Admin pages are reference and setup pages. They should not replace the live Console controls.",
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
                        owner: "Runbook",
                        purpose: "How to operate, expected healthy results, failure signs, and troubleshooting flow.",
                    },
                    {
                        label: "Model Profiles",
                        route: "/admin/models",
                        owner: "Model routing",
                        purpose: "Default A-E and user-created model profiles for chat, TTS, ASR, Live2D selection, API keys, and local model base URLs.",
                    },
                    {
                        label: "Characters",
                        route: "/admin/characters",
                        owner: "Character setup",
                        purpose: "Role prompt plus model profile binding. This is the character-facing layer above Model Profiles.",
                    },
                    {
                        label: "Channels",
                        route: "/admin/channels",
                        owner: "Messaging gateways",
                        purpose: "Telegram / Discord settings and smoke readiness, with QQ, LINE, WhatsApp, and later adapters kept in one gateway boundary.",
                    },
                    {
                        label: "Open WebUI Bridge",
                        route: "/admin/openwebui",
                        owner: "Operator bridge",
                        purpose: "Narrow OpenAPI tool bridge status and setup notes for Open WebUI.",
                    },
                ],
            },
            {
                title: "API namespace boundaries",
                body: "APIs are grouped by product surface. Browser pages call narrow namespaces instead of sharing one mixed endpoint.",
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
                        purpose: "Messages, jobs, session storage, role cards, uploads, and downloads.",
                    },
                    {
                        label: "Stage API",
                        route: "/api/stage/events",
                        owner: "Stage event broker",
                        purpose: "User/session-scoped publish and SSE subscribe for subtitles and stage state.",
                    },
                    {
                        label: "Admin/bridge API",
                        route: "/api/character-profiles*, /api/model-profiles*, /api/channels*, /api/openwebui/*, /api/health",
                        owner: "Back office",
                        purpose: "Character setup, model profile persistence, messaging channel config/status, Open WebUI bridge tools, health checks, and protected docs.",
                    },
                ],
            },
            {
                title: "Routing rules",
                body: "These rules keep the system readable as more pages and channel integrations are added.",
                items: [
                    "Do not put live operator controls on Stage. Stage is display-only for a selected session.",
                    "Do not give Messenger tool execution by default. Messenger remains chat-only unless a later approval gate is added.",
                    "Put long-running setup, model routing, and reference material under Admin child pages.",
                    "Keep Console focused on real-time operation and current session work.",
                    "External channel gateways should start with config, secret redaction, and smoke checks in `/admin/channels`, then be wired to runtime adapters.",
                ],
            },
        ],
    },
    "zh-Hant": {
        sections: [
            {
                title: "第一層產品入口",
                body: "用使用者角色與工作目的分 route。Stage 是展示，Messenger 是通訊，Console 是操作，Admin 是管理參考。",
                cards: [
                    {
                        label: "前台 Stage",
                        route: "/stage?session_name=<name>",
                        owner: "純顯示畫面",
                        purpose: "單一 session 的角色畫面、字幕、TTS 播放與 Live2D lip sync。",
                    },
                    {
                        label: "通訊 Messenger",
                        route: "/messenger?session_name=<name>",
                        owner: "通訊入口",
                        purpose: "輕量聊天室，將 assistant 最終文字送到 Stage。",
                    },
                    {
                        label: "中台 Console",
                        route: "/console",
                        owner: "操作員工作台",
                        purpose: "sessions、角色卡、ASR、TTS、Live2D、jobs、CRON、HEARTBEAT 的完整 runtime 控制面。",
                    },
                    {
                        label: "後台 Admin",
                        route: "/admin",
                        owner: "後台索引",
                        purpose: "受保護入口，集中 health、API docs、模型設定、Open WebUI bridge 與文件頁。",
                    },
                ],
            },
            {
                title: "Console 頁面內部結構",
                body: "Console 保持單一操作員工作台。面板依責任分區，不依裝飾或臨時功能堆疊。",
                cards: [
                    {
                        label: "Stage panel",
                        route: "/console 左側",
                        owner: "視覺 runtime",
                        purpose: "連線狀態、session badge、目前模型 profile、語言/顯示切換、Live2D 舞台與 Live2D drawer。",
                    },
                    {
                        label: "控制抽屜",
                        route: "Console side panels",
                        owner: "操作設定",
                        purpose: "Session 清單與角色卡選擇/編輯；資料必須維持 trusted user scope。",
                    },
                    {
                        label: "設定群組",
                        route: "Console details panels",
                        owner: "Runtime configuration",
                        purpose: "Route mode、provider/runtime safety、ASR、TTS、舞台資產、CRON 與 HEARTBEAT。",
                    },
                    {
                        label: "對話區",
                        route: "/api/chat* + /api/sessions*",
                        owner: "即時操作",
                        purpose: "目前 session transcript、agent trace、attachments、麥克風輸入與送出控制。",
                    },
                ],
            },
            {
                title: "Admin 子頁面",
                body: "Admin 子頁面是參考與設定入口，不取代即時 Console 控制。",
                cards: [
                    {
                        label: "網站結構",
                        route: "/admin/structure",
                        owner: "資訊架構",
                        purpose: "Route map、頁面邊界、Console 分區與 API namespace 分組。",
                    },
                    {
                        label: "操作說明",
                        route: "/admin/guide",
                        owner: "Runbook",
                        purpose: "如何操作、正常預期、故障跡象與排除流程。",
                    },
                    {
                        label: "模型設定",
                        route: "/admin/models",
                        owner: "模型路由",
                        purpose: "預設 A-E 與使用者新增的模型 profile；管理 chat、TTS、ASR、Live2D 選擇、API key 與地端模型 base URL。",
                    },
                    {
                        label: "角色設定",
                        route: "/admin/characters",
                        owner: "角色設定",
                        purpose: "角色 prompt 加上模型 profile 綁定，是 Model Profiles 上方的角色產品層。",
                    },
                    {
                        label: "通訊平台",
                        route: "/admin/channels",
                        owner: "Messaging gateways",
                        purpose: "Telegram / Discord 設定與 smoke readiness；QQ、LINE、WhatsApp 與後續 adapter 維持在同一 gateway 邊界。",
                    },
                    {
                        label: "Open WebUI Bridge",
                        route: "/admin/openwebui",
                        owner: "操作員 bridge",
                        purpose: "Open WebUI narrow OpenAPI tool bridge 的狀態與接線說明。",
                    },
                ],
            },
            {
                title: "API namespace 邊界",
                body: "API 依產品面分組。Browser 頁面呼叫窄 namespace，不共用混雜的大入口。",
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
                        owner: "Chat runtime",
                        purpose: "Messages、jobs、session storage、角色卡、uploads 與 downloads。",
                    },
                    {
                        label: "Stage API",
                        route: "/api/stage/events",
                        owner: "Stage event broker",
                        purpose: "以 user/session scope 做字幕與舞台狀態 publish/SSE subscribe。",
                    },
                    {
                        label: "Admin/Bridge API",
                        route: "/api/character-profiles*, /api/model-profiles*, /api/channels*, /api/openwebui/*, /api/health",
                        owner: "後台",
                        purpose: "角色設定、模型 profile、通訊平台 config/status、Open WebUI bridge tools、health checks 與 protected docs。",
                    },
                ],
            },
            {
                title: "Route 增長規則",
                body: "之後新增頁面與通訊平台時，用這幾條規則保持乾淨。",
                items: [
                    "Stage 不放即時操作控制；它只顯示選定 session 的結果。",
                    "Messenger 預設不給工具執行；除非後續加 approval gate，否則維持 chat-only。",
                    "長期設定、模型路由、參考文件放在 Admin 子頁面。",
                    "Console 專注即時操作與目前 session 工作。",
                    "外部通道先在 `/admin/channels` 建立設定、secret 遮罩與 smoke check，再接 runtime adapter。",
                ],
            },
        ],
    },
    "zh-Hans": {
        sections: [
            {
                title: "第一层产品入口",
                body: "用使用者角色与工作目的分 route。Stage 是展示，Messenger 是通讯，Console 是操作，Admin 是管理参考。",
                cards: [
                    {
                        label: "前台 Stage",
                        route: "/stage?session_name=<name>",
                        owner: "纯显示画面",
                        purpose: "单一 session 的角色画面、字幕、TTS 播放与 Live2D lip sync。",
                    },
                    {
                        label: "通讯 Messenger",
                        route: "/messenger?session_name=<name>",
                        owner: "通讯入口",
                        purpose: "轻量聊天室，将 assistant 最终文字送到 Stage。",
                    },
                    {
                        label: "中台 Console",
                        route: "/console",
                        owner: "操作员工作台",
                        purpose: "sessions、角色卡、ASR、TTS、Live2D、jobs、CRON、HEARTBEAT 的完整 runtime 控制面。",
                    },
                    {
                        label: "后台 Admin",
                        route: "/admin",
                        owner: "后台索引",
                        purpose: "受保护入口，集中 health、API docs、模型设置、Open WebUI bridge 与文档页。",
                    },
                ],
            },
            {
                title: "Console 页面内部结构",
                body: "Console 保持单一操作员工作台。面板依责任分区，不依装饰或临时功能堆叠。",
                cards: [
                    {
                        label: "Stage panel",
                        route: "/console 左侧",
                        owner: "视觉 runtime",
                        purpose: "连接状态、session badge、当前模型 profile、语言/显示切换、Live2D 舞台与 Live2D drawer。",
                    },
                    {
                        label: "控制抽屉",
                        route: "Console side panels",
                        owner: "操作设置",
                        purpose: "Session 清单与角色卡选择/编辑；数据必须维持 trusted user scope。",
                    },
                    {
                        label: "设置群组",
                        route: "Console details panels",
                        owner: "Runtime configuration",
                        purpose: "Route mode、provider/runtime safety、ASR、TTS、舞台资产、CRON 与 HEARTBEAT。",
                    },
                    {
                        label: "对话区",
                        route: "/api/chat* + /api/sessions*",
                        owner: "即时操作",
                        purpose: "当前 session transcript、agent trace、attachments、麦克风输入与发送控制。",
                    },
                ],
            },
            {
                title: "Admin 子页面",
                body: "Admin 子页面是参考与设置入口，不取代即时 Console 控制。",
                cards: [
                    {
                        label: "网站结构",
                        route: "/admin/structure",
                        owner: "信息架构",
                        purpose: "Route map、页面边界、Console 分区与 API namespace 分组。",
                    },
                    {
                        label: "操作说明",
                        route: "/admin/guide",
                        owner: "Runbook",
                        purpose: "如何操作、正常预期、故障迹象与排除流程。",
                    },
                    {
                        label: "模型设置",
                        route: "/admin/models",
                        owner: "模型路由",
                        purpose: "默认 A-E 与用户新增的模型 profile；管理 chat、TTS、ASR、Live2D 选择、API key 与地端模型 base URL。",
                    },
                    {
                        label: "角色设置",
                        route: "/admin/characters",
                        owner: "角色设置",
                        purpose: "角色 prompt 加上模型 profile 绑定，是 Model Profiles 上方的角色产品层。",
                    },
                    {
                        label: "通讯平台",
                        route: "/admin/channels",
                        owner: "Messaging gateways",
                        purpose: "Telegram / Discord 设置与 smoke readiness；QQ、LINE、WhatsApp 与后续 adapter 维持在同一 gateway 边界。",
                    },
                    {
                        label: "Open WebUI Bridge",
                        route: "/admin/openwebui",
                        owner: "操作员 bridge",
                        purpose: "Open WebUI narrow OpenAPI tool bridge 的状态与接线说明。",
                    },
                ],
            },
            {
                title: "API namespace 边界",
                body: "API 依产品面分组。Browser 页面调用窄 namespace，不共用混杂的大入口。",
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
                        owner: "Chat runtime",
                        purpose: "Messages、jobs、session storage、角色卡、uploads 与 downloads。",
                    },
                    {
                        label: "Stage API",
                        route: "/api/stage/events",
                        owner: "Stage event broker",
                        purpose: "以 user/session scope 做字幕与舞台状态 publish/SSE subscribe。",
                    },
                    {
                        label: "Admin/Bridge API",
                        route: "/api/character-profiles*, /api/model-profiles*, /api/channels*, /api/openwebui/*, /api/health",
                        owner: "后台",
                        purpose: "角色设置、模型 profile、通讯平台 config/status、Open WebUI bridge tools、health checks 与 protected docs。",
                    },
                ],
            },
            {
                title: "Route 增长规则",
                body: "之后新增页面与通讯平台时，用这几条规则保持干净。",
                items: [
                    "Stage 不放即时操作控制；它只显示选定 session 的结果。",
                    "Messenger 默认不给工具执行；除非后续加 approval gate，否则维持 chat-only。",
                    "长期设置、模型路由、参考文档放在 Admin 子页面。",
                    "Console 专注即时操作与当前 session 工作。",
                    "外部通道先在 `/admin/channels` 建立设置、secret 遮罩与 smoke check，再接 runtime adapter。",
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

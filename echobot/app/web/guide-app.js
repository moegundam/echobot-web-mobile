import { initShellI18n } from "./shell-i18n.js?v=admin-boundary-1";
import { initShellDisplayMode } from "./shell-display-mode.js?v=site-public-6";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

const guideContent = {
    en: {
        sections: [
            {
                title: "What each page is for",
                body: "EchoBot is split into four product entrances so testing and operation stay clear.",
                items: [
                    "Stage shows the character, subtitles, TTS playback, and Live2D lip sync for one session.",
                    "Messenger is the lightweight chat entrance. In v1 it should stay chat-only and publish final replies to Stage.",
                    "Console is the existing full control surface for sessions, role cards, ASR, TTS, Live2D, runtime controls, CRON, and HEARTBEAT.",
                    "Admin is the protected index for health, docs, jobs, site structure, this guide, and setup pages.",
                ],
            },
            {
                title: "Basic operation flow",
                body: "Use the same session name when you want Messenger, Console, and Stage to refer to the same conversation.",
                items: [
                    "Open Stage with `/stage?session_name=demo` and keep it visible for display and subtitles.",
                    "Open Messenger with the same session name, send a message, and confirm Stage receives the assistant final event.",
                    "Open Console when you need to change providers, role cards, route mode, runtime safety, Live2D, backgrounds, CRON, or HEARTBEAT.",
                    "Open Admin before testing to check `/api/health`, API docs, active jobs, and the current guide.",
                ],
            },
            {
                title: "Configuration checklist",
                body: "For local tunnel testing, keep the EchoBot server private and let Cloudflare Access provide HTTPS and login.",
                items: [
                    "Run EchoBot on `127.0.0.1:8000` for local tunnel mode. Do not expose `0.0.0.0` unless you are using the VPS profile.",
                    "Enable trusted-user header mode when sharing with testers: `ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true` and `ECHOBOT_TRUSTED_USER_REQUIRED=true`.",
                    "Use an OpenAI-compatible profile such as private LiteLLM for low-cost private testing, or switch to another private provider when it is ready.",
                    "Keep secrets in local env files only. API keys, Cloudflare tokens, and provider credentials must not be committed.",
                    "Use `chat_only` for Messenger. Use Console when you intentionally want tool-capable Agent behavior.",
                ],
            },
            {
                title: "Expected healthy result",
                body: "A healthy local-tunnel test should be boring and repeatable.",
                items: [
                    "Admin health returns JSON and shows the trusted user when header mode is enabled.",
                    "Messenger streams an assistant reply and returns to ready state after completion.",
                    "Stage updates subtitles on assistant final events and starts TTS only after the final response.",
                    "ASR pauses while TTS is playing and resumes after playback when always-on microphone is enabled.",
                    "A second tester cannot see another tester's sessions, jobs, attachments, or Stage events.",
                ],
            },
            {
                title: "What counts as a failure",
                body: "Treat these symptoms as failures instead of normal variance.",
                items: [
                    "A protected page or `/api/*` works without Cloudflare Access or a trusted user header while protection is enabled.",
                    "Stage receives another user's subtitles or a different session's events.",
                    "Messenger triggers tool execution when it is expected to be chat-only.",
                    "The microphone button stays busy after permission is denied, the page goes background, or TTS playback finishes.",
                    "TTS audio plays but Stage subtitle or Live2D lip sync does not update for the final reply.",
                    "Disk, logs, or `.echobot/users/<user_id>/...` grow unexpectedly during a small 10-person test.",
                ],
            },
            {
                title: "Troubleshooting flow",
                body: "Start with the smallest layer, then move outward. Record the failing step and evidence.",
                items: [
                    "Check server health first: `/api/health`, terminal logs, and whether the EchoBot process is still running.",
                    "Check identity next: confirm Cloudflare Access login, trusted user header presence, and that missing or invalid headers return 401.",
                    "Check session scope: compare the session name in Stage, Messenger, and Console, then test with a second user header.",
                    "Check provider config: verify `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, TTS provider, and ASR provider values.",
                    "Check browser behavior: use HTTPS for microphone tests, reload after permission changes, and inspect console errors.",
                    "If the issue repeats, write a troubleshooting record with commands, timestamps, logs, root cause, fix, and verification.",
                ],
            },
        ],
    },
    "zh-Hant": {
        sections: [
            {
                title: "各頁面的用途",
                body: "EchoBot 目前拆成四個產品入口，讓展示、操作與管理的邊界清楚。",
                items: [
                    "前台 Stage 顯示角色、字幕、TTS 播放與 Live2D lip sync，並綁定單一 session。",
                    "通訊 Messenger 是輕量聊天入口。v1 預設只做純聊天，並把最終回覆發布到 Stage。",
                    "中台 Console 是既有完整控制介面，用於 sessions、角色卡、ASR、TTS、Live2D、runtime 控制、CRON 與 HEARTBEAT。",
                    "後台 Admin 是受保護索引，用於 health、API docs、jobs、網站結構、本說明頁與設定頁。",
                ],
            },
            {
                title: "基本操作流程",
                body: "當你希望 Messenger、Console、Stage 指向同一段對話時，三邊使用同一個 session name。",
                items: [
                    "用 `/stage?session_name=demo` 開前台，保持畫面可見，用來顯示角色與字幕。",
                    "用相同 session name 開 Messenger，送出訊息，確認 Stage 收到 assistant final event。",
                    "需要調整 provider、角色卡、路由模式、安全權限、Live2D、背景、CRON 或 HEARTBEAT 時才開 Console。",
                    "測試前先開 Admin，確認 `/api/health`、API docs、active jobs 與操作說明都可讀。",
                ],
            },
            {
                title: "設定檢查清單",
                body: "Local Tunnel 測試時，EchoBot server 應保持本機私有，由 Cloudflare Access 提供 HTTPS 與登入。",
                items: [
                    "Local Tunnel 模式使用 `127.0.0.1:8000` 啟動 EchoBot。除非是 VPS profile，否則不要改成 `0.0.0.0`。",
                    "分享給內測者時啟用 trusted-user header：`ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true` 與 `ECHOBOT_TRUSTED_USER_REQUIRED=true`。",
                    "低成本私有測試可使用私有 LiteLLM 這類 OpenAI-compatible profile；其他私有 provider 完成後再切換。",
                    "Secrets 只放本機 env。API keys、Cloudflare tokens、provider credentials 不可進 repo。",
                    "Messenger 使用 `chat_only`。需要工具型 Agent 行為時才走 Console。",
                ],
            },
            {
                title: "正常時的預期成果",
                body: "健康的 Local Tunnel 測試應該穩定、可重複，而且行為明確。",
                items: [
                    "Admin health 回傳 JSON；啟用 header 模式時會顯示 trusted user。",
                    "Messenger 能串流 assistant 回覆，完成後狀態回到就緒。",
                    "Stage 在 assistant final event 後更新字幕，並且只在最終回覆後開始 TTS。",
                    "開啟常開麥時，TTS 播放期間 ASR 暫停，播放結束後恢復。",
                    "第二位測試者看不到另一位測試者的 sessions、jobs、attachments 或 Stage events。",
                ],
            },
            {
                title: "哪些狀況算故障",
                body: "下列現象要當成故障處理，不要視為正常浮動。",
                items: [
                    "保護模式已啟用時，protected page 或 `/api/*` 不經 Cloudflare Access 或 trusted user header 也能進入。",
                    "Stage 收到其他 user 的字幕，或收到不同 session 的事件。",
                    "Messenger 在預期純聊天時觸發工具型 Agent 執行。",
                    "麥克風權限被拒、頁面進背景或 TTS 結束後，錄音按鈕仍卡在 busy 狀態。",
                    "TTS 有聲音，但 Stage 字幕或 Live2D lip sync 沒跟最終回覆更新。",
                    "10 人小規模測試時，disk、log 或 `.echobot/users/<user_id>/...` 異常快速成長。",
                ],
            },
            {
                title: "故障排除流程",
                body: "從最小層開始查，再往外擴。每一步都記錄失敗點與證據。",
                items: [
                    "先查 server health：`/api/health`、terminal logs、EchoBot process 是否仍在執行。",
                    "再查身份層：Cloudflare Access 是否登入、trusted user header 是否存在、缺失或非法 header 是否回 401。",
                    "查 session scope：比對 Stage、Messenger、Console 的 session name，再用第二個 user header 驗證隔離。",
                    "查 provider 設定：確認 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、TTS provider、ASR provider。",
                    "查瀏覽器行為：麥克風測試必須 HTTPS，變更權限後重新載入，並檢查 console errors。",
                    "如果問題可重現，建立 troubleshooting record，寫入指令、時間、log、根因、修復與驗證方式。",
                ],
            },
        ],
    },
    "zh-Hans": {
        sections: [
            {
                title: "各页面的用途",
                body: "EchoBot 目前拆成四个产品入口，让展示、操作与管理边界清楚。",
                items: [
                    "前台 Stage 显示角色、字幕、TTS 播放与 Live2D lip sync，并绑定单一 session。",
                    "通讯 Messenger 是轻量聊天入口。v1 默认只做纯聊天，并把最终回复发布到 Stage。",
                    "中台 Console 是既有完整控制界面，用于 sessions、角色卡、ASR、TTS、Live2D、runtime 控制、CRON 与 HEARTBEAT。",
                    "后台 Admin 是受保护索引，用于 health、API docs、jobs、网站结构、本说明页与设置页。",
                ],
            },
            {
                title: "基本操作流程",
                body: "当你希望 Messenger、Console、Stage 指向同一段对话时，三边使用同一个 session name。",
                items: [
                    "用 `/stage?session_name=demo` 打开前台，保持画面可见，用来显示角色与字幕。",
                    "用相同 session name 打开 Messenger，发送消息，确认 Stage 收到 assistant final event。",
                    "需要调整 provider、角色卡、路由模式、安全权限、Live2D、背景、CRON 或 HEARTBEAT 时才打开 Console。",
                    "测试前先打开 Admin，确认 `/api/health`、API docs、active jobs 与操作说明都可读。",
                ],
            },
            {
                title: "设置检查清单",
                body: "Local Tunnel 测试时，EchoBot server 应保持本机私有，由 Cloudflare Access 提供 HTTPS 与登录。",
                items: [
                    "Local Tunnel 模式使用 `127.0.0.1:8000` 启动 EchoBot。除非是 VPS profile，否则不要改成 `0.0.0.0`。",
                    "分享给内测者时启用 trusted-user header：`ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true` 与 `ECHOBOT_TRUSTED_USER_REQUIRED=true`。",
                    "低成本私有测试可使用私有 LiteLLM 这类 OpenAI-compatible profile；其他私有 provider 完成后再切换。",
                    "Secrets 只放本机 env。API keys、Cloudflare tokens、provider credentials 不可进 repo。",
                    "Messenger 使用 `chat_only`。需要工具型 Agent 行为时才走 Console。",
                ],
            },
            {
                title: "正常时的预期结果",
                body: "健康的 Local Tunnel 测试应该稳定、可重复，而且行为明确。",
                items: [
                    "Admin health 返回 JSON；启用 header 模式时会显示 trusted user。",
                    "Messenger 能串流 assistant 回复，完成后状态回到就绪。",
                    "Stage 在 assistant final event 后更新字幕，并且只在最终回复后开始 TTS。",
                    "开启常开麦时，TTS 播放期间 ASR 暂停，播放结束后恢复。",
                    "第二位测试者看不到另一位测试者的 sessions、jobs、attachments 或 Stage events。",
                ],
            },
            {
                title: "哪些状况算故障",
                body: "下列现象要当成故障处理，不要视为正常波动。",
                items: [
                    "保护模式已启用时，protected page 或 `/api/*` 不经 Cloudflare Access 或 trusted user header 也能进入。",
                    "Stage 收到其他 user 的字幕，或收到不同 session 的事件。",
                    "Messenger 在预期纯聊天时触发工具型 Agent 执行。",
                    "麦克风权限被拒、页面进后台或 TTS 结束后，录音按钮仍卡在 busy 状态。",
                    "TTS 有声音，但 Stage 字幕或 Live2D lip sync 没跟最终回复更新。",
                    "10 人小规模测试时，disk、log 或 `.echobot/users/<user_id>/...` 异常快速增长。",
                ],
            },
            {
                title: "故障排除流程",
                body: "从最小层开始查，再往外扩。每一步都记录失败点与证据。",
                items: [
                    "先查 server health：`/api/health`、terminal logs、EchoBot process 是否仍在运行。",
                    "再查身份层：Cloudflare Access 是否登录、trusted user header 是否存在、缺失或非法 header 是否回 401。",
                    "查 session scope：比对 Stage、Messenger、Console 的 session name，再用第二个 user header 验证隔离。",
                    "查 provider 设置：确认 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、TTS provider、ASR provider。",
                    "查浏览器行为：麦克风测试必须 HTTPS，变更权限后重新加载，并检查 console errors。",
                    "如果问题可重现，建立 troubleshooting record，写入指令、时间、log、根因、修复与验证方式。",
                ],
            },
        ],
    },
};

const contentRoot = document.getElementById("guide-content");
const i18n = initShellI18n({
    onChange: () => {
        renderGuide();
        displayMode.refresh();
    },
});
const displayMode = initShellDisplayMode({ t: i18n.t });
initShellSessionLinks();

renderGuide();

function renderGuide() {
    if (!contentRoot) {
        return;
    }

    const content = guideContent[i18n.language] || guideContent.en;
    contentRoot.replaceChildren(
        ...content.sections.map((section, index) => buildGuideSection(section, index)),
    );
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

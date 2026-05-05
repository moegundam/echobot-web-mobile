import { initShellI18n } from "./shell-i18n.js?v=session-centered-2";
import { initShellDisplayMode } from "./shell-display-mode.js?v=session-centered-2";
import { initShellSessionLinks } from "./shell-session-links.js?v=site-public-6";

const guideContent = {
    en: {
        sections: [
            {
                title: "Session-centered pages",
                body: "Use this order for predictable testing: configure resources, bind a character, create/select session, then test through Console, Messenger, and Stage.",
                items: [
                    "Stage is the single-session display surface for character, subtitles, TTS playback, and Live2D.",
                    "Messenger is the lightweight chat entrance that shows and verifies assistant output on Stage by session.",
                    "Console is the live session workbench for runtime controls and character-role switches.",
                    "Admin is the setup hub for models, characters, channels, and documentation pages.",
                ],
            },
            {
                title: "Recommended setup order",
                body: "Complete setup before opening tests; this makes issue tracking easy and keeps session behavior stable.",
                items: [
                    "Admin → LLM setup: open `/admin/models` and configure the model profile for the target model provider.",
                    "Admin → Voice setup: open `/admin/voice-models` and configure STT/TTS voice settings.",
                    "Admin → Live2D setup: open `/admin/live2d` and configure the visual model profile.",
                    "Admin → Characters: open `/admin/characters` and bind LLM profile + voice profile + Live2D profile to one character.",
                ],
            },
            {
                title: "Session test flow",
                body: "After setup, create a session context and verify one path end-to-end with the same session name.",
                items: [
                    "In `/admin/sessions`, create or select the session to test.",
                    "In `/console`, open the same session and choose the prepared character card.",
                    "Select an optional channel for the session (if needed): Telegram/Discord is currently smoke-test ready; other channels are planned.",
                    "Use `/messenger?session_name=<name>` to send a message and confirm the final assistant reply updates Stage.",
                    "Use `/stage?session_name=<name>` only as result display during verification.",
                ],
            },
            {
                title: "Channels and boundaries",
                body: "Channels are entry points, not the session core. They decide who can send into a session.",
                items: [
                    "Telegram/Discord currently support smoke tests in the current workflow.",
                    "LINE, WhatsApp, QQ, and others are planned and not part of the regular test path yet.",
                    "Open WebUI bridge is not a chat channel; it is an operator tool API interface.",
                    "Keep session + character controls in Console and keep channels in setup context.",
                ],
            },
            {
                title: "Open WebUI bridge",
                body: "Use Open WebUI for operator tooling, not as the default live test entry.",
                items: [
                    "Open `/admin/openwebui` to configure allowed tool methods and operator-level bridge status.",
                    "Use the bridge for integration testing of tools only after the session flow is stable.",
                    "Validate tool-driven operations from Console context and keep chat verification on Messenger/Stage.",
                ],
            },
            {
                title: "Healthy test criteria",
                body: "If the following is true, the session-centered path is in good shape.",
                items: [
                    "The same session name is used across Console, Messenger, and Stage.",
                    "Messenger receives expected replies and Stage renders the same final output with subtitles.",
                    "Character, model, and Live2D changes take effect only for the selected session context.",
                    "Open WebUI bridge calls are treated as operator tool operations, not chat routing changes.",
                ],
            },
        ],
    },
    "zh-Hant": {
        sections: [
            {
                title: "以 Session 為核心的頁面",
                body: "建議用固定順序測試：先設定資源，完成角色綁定，建立/選擇 Session，最後用 Console、Messenger、Stage 驗證。",
                items: [
                    "前台 Stage 是單一 session 的呈現面，顯示角色、字幕、TTS 與 Live2D。",
                    "通訊 Messenger 是輕量聊天入口，會依 session 驗證並將最終文字回傳到 Stage。",
                    "中台 Console 是即時操作主控台，用來切換角色、角色卡與 session 的 runtime。",
                    "後台 Admin 是設定中樞，負責模型、角色、通道與文件頁面。",
                ],
            },
            {
                title: "推薦設定順序",
                body: "先完成設定可降低測試變因，讓問題回溯只跟 session 有關。",
                items: [
                    "後台流程第一步：在 `/admin/models` 設定可用的 LLM profile。",
                    "第二步：在 `/admin/voice-models` 設定 STT/TTS 相關語音設定。",
                    "第三步：在 `/admin/live2d` 設定 Live2D 視覺 profile。",
                    "第四步：到 `/admin/characters` 將 LLM、Voice、Live2D 綁到同一個角色設定。",
                ],
            },
            {
                title: "Session 測試順序",
                body: "完成設定後，建立一個測試 session 並用同一 session name 完成前後端驗證。",
                items: [
                    "在 `/admin/sessions` 建立或選擇本次測試 session。",
                    "在 `/console` 開啟同 session，選擇事先綁定的角色卡。",
                    "視需求為 session 選擇通道（Telegram/Discord）並確認能進入測試。",
                    "在 `/messenger?session_name=<name>` 傳一則訊息，確認 Messenger 最終回覆同步到 Stage。",
                    "用 `/stage?session_name=<name>` 僅檢視結果畫面（字幕/TTS/Live2D）。",
                ],
            },
            {
                title: "通道與邊界",
                body: "通道是進入口，不是核心運行邏輯；核心是 session、角色與 runtime 控制。",
                items: [
                    "目前可做 smoke test 的通道為 Telegram / Discord。",
                    "LINE、WhatsApp、QQ 等仍是規劃中，暫不列入常規測試流程。",
                    "Open WebUI bridge 是操作員工具介面，不是對話通道。",
                    "核心驗證都應在 `/console`、`/messenger`、`/stage` 的同 session 流程中完成。",
                ],
            },
            {
                title: "Open WebUI bridge",
                body: "Open WebUI 只用來做操作員工具串接與驗證，與日常對話測試分開。",
                items: [
                    "在 `/admin/openwebui` 設定工具方法白名單與 bridge 狀態。",
                    "先完成 session 流程後，再做 bridge 的工具型驗證。",
                    "聊天室測試仍以 Messenger + Stage + Console 為主。",
                ],
            },
            {
                title: "健康檢核",
                body: "以下都成立時，代表 Session-centered 操作流程已順暢。",
                items: [
                    "Console、Messenger、Stage 使用同一個 session_name。",
                    "Messenger 回覆在 Stage 上有一致字幕與輸出。",
                    "角色與模型變更只影響到該 session 上下文。",
                    "Open WebUI 僅留在操作員工具路徑，不改變一般通道驗證結果。",
                ],
            },
        ],
    },
    "zh-Hans": {
        sections: [
            {
                title: "以 Session 为核心的页面",
                body: "建议固定顺序：先配置资源，完成角色绑定，建立/选择 Session，最后用 Console、Messenger、Stage 做联动验证。",
                items: [
                    "前台 Stage 是单一 session 的显示面，展示角色、字幕、TTS 与 Live2D。",
                    "通讯 Messenger 是轻量聊天入口，按 session 验证并将最终文本回传到 Stage。",
                    "中台 Console 是实时操作主控台，用于切换角色、角色卡与 session 的运行参数。",
                    "后台 Admin 是设置中枢，负责模型、角色、通道和文档页。",
                ],
            },
            {
                title: "推荐设置顺序",
                body: "先完成设置可减少测试波动，故障回溯也只围绕 session。",
                items: [
                    "第一步：在 `/admin/models` 配置可用的 LLM profile。",
                    "第二步：在 `/admin/voice-models` 配置 STT/TTS 语音设置。",
                    "第三步：在 `/admin/live2d` 配置 Live2D 视觉 profile。",
                    "第四步：到 `/admin/characters` 将 LLM、Voice、Live2D 绑定到同一角色配置。",
                ],
            },
            {
                title: "Session 测试顺序",
                body: "完成设置后，创建一个测试 session，并通过同一 session_name 做端到端验证。",
                items: [
                    "在 `/admin/sessions` 创建或选择本次测试 session。",
                    "在 `/console` 打开同一 session，并选择预先绑定的角色卡。",
                    "按需为 session 选通道（Telegram/Discord），并确认可进入测试。",
                    "在 `/messenger?session_name=<name>` 发一条消息，确认 Assistant 最终回复同步到 Stage。",
                    "用 `/stage?session_name=<name>` 仅验证结果输出（字幕/TTS/Live2D）。",
                ],
            },
            {
                title: "通道与边界",
                body: "通道是入口，不是核心；核心是 session、角色与 runtime 控制。",
                items: [
                    "目前可做 smoke test 的通道是 Telegram / Discord。",
                    "LINE、WhatsApp、QQ 等仍在规划中，暂不作为常规测试入口。",
                    "Open WebUI bridge 是操作员工具接口，不是对话通道。",
                    "核心验证仍以 `/console`、`/messenger`、`/stage` 的同 session 流程为准。",
                ],
            },
            {
                title: "Open WebUI bridge",
                body: "Open WebUI 仅用于操作员工具对接和验证，和普通对话测试路径分离。",
                items: [
                    "在 `/admin/openwebui` 配置允许的工具方法与 bridge 状态。",
                    "先让 session 流程稳定后，再做工具接口验证。",
                    "聊天验证仍以 Messenger + Stage + Console 为主。",
                ],
            },
            {
                title: "健康检核",
                body: "以下都满足时，Session-centered 操作流程可视为正常。",
                items: [
                    "Console、Messenger、Stage 的 session_name 一致。",
                    "Messenger 回答在 Stage 上有一致字幕与输出。",
                    "角色、模型变更仅影响当前 session 上下文。",
                    "Open WebUI 只留在操作员工具路径，不改变普通通道验证结论。",
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

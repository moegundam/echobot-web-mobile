import { initShellI18n } from "./shell-i18n.js?v=language-menu-1";
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
                    "Admin → LLM setup: open `/admin/models` and configure the LLM profile for the target provider.",
                    "Admin → Voice setup: open `/admin/voice-models` and configure STT/TTS voice settings.",
                    "Admin → Live2D setup: open `/admin/live2d` and configure the Live2D visual profile.",
                    "Admin → Characters: open `/admin/characters` and bind LLM profile + voice profile + Live2D profile to one character.",
                ],
            },
            {
                title: "Session test flow",
                body: "After setup, create a session context and verify one path end-to-end with the same session name.",
                items: [
                    "In `/admin/sessions`, create or select the session to test.",
                    "In `/console`, open the same session and choose the prepared character card.",
                    "Select an optional channel for the session (if needed): Telegram is polling-ready, and Discord supports protected webhook plus native bot events when configured.",
                    "Use `/messenger?session_name=<name>` to send a message and confirm the final assistant reply updates Stage.",
                    "Use `/stage?session_name=<name>` only as result display during verification.",
                ],
            },
            {
                title: "Channels and boundaries",
                body: "Channels are entry points, not the session core. They decide who can send into a session.",
                items: [
                    "Telegram supports Bot API polling; Discord supports a protected webhook bridge and native bot events with Message Content Intent enabled.",
                    "QQ has a built-in adapter entry but is not part of the verified regular test path; LINE and WhatsApp remain planned.",
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
                title: "Before private sharing",
                body: "Run these checks before pushing changes or exposing the local tunnel to testers.",
                items: [
                    "Run `python scripts/check_public_safety.py` and confirm it passes.",
                    "Run `git status --short` and confirm `.echobot/`, `.env`, bot tokens, and bridge tokens are not tracked.",
                    "Use `/admin/channels` local E2E first; use real Telegram/Discord only after allow_from is restricted.",
                    "Use `/admin/openwebui` and `scripts/openwebui_bridge_smoke.py` before enabling Open WebUI tools.",
                ],
            },
            {
                title: "Failure signs and first checks",
                body: "When behavior looks wrong, check the session boundary first before changing model or channel settings.",
                items: [
                    "Stage does not update: confirm Console, Messenger, and Stage use the same session, then refresh `/stage?session_name=<name>`.",
                    "Character or Live2D does not change: use Console Apply to Stage for temporary runtime changes, or save the persistent binding in Admin → Characters/Sessions.",
                    "Messenger replies in the wrong language: check the UI language and the character prompt; explicit prompt language has priority.",
                    "Telegram/Discord does not mirror to Stage: open `/admin/channels`, confirm the bot is running, `mirror_to_stage` is enabled, and the stage session name is correct.",
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
                title: "以場次為核心的頁面",
                body: "建議用固定順序測試：先設定資源，完成角色綁定，建立/選擇場次，最後用 Console、Messenger、Stage 驗證。",
                items: [
                    "前台 Stage 是單一場次的呈現面，顯示角色、字幕、TTS 與 Live2D。",
                    "通訊 Messenger 是輕量聊天入口，會依場次驗證並將最終文字回傳到 Stage。",
                    "中台 Console 是即時操作主控台，用來切換角色、角色卡與場次 runtime。",
                    "後台 Admin 是設定中樞，負責模型、角色、通道與文件頁面。",
                ],
            },
            {
                title: "推薦設定順序",
                body: "先完成設定可降低測試變因，讓問題回溯只跟場次有關。",
                items: [
                    "後台流程第一步：在 `/admin/models` 設定可用的 LLM profile。",
                    "第二步：在 `/admin/voice-models` 設定 STT/TTS 相關語音設定。",
                    "第三步：在 `/admin/live2d` 設定 Live2D 視覺 profile。",
                    "第四步：到 `/admin/characters` 將 LLM、Voice、Live2D 綁到同一個角色設定。",
                ],
            },
            {
                title: "場次測試順序",
                body: "完成設定後，建立一個測試場次並用同一場次名稱完成前後端驗證。",
                items: [
                    "在 `/admin/sessions` 建立或選擇本次測試場次。",
                    "在 `/console` 開啟同一場次，選擇事先綁定的角色卡。",
                    "視需求為場次選擇通訊入口；Telegram 可用 polling，Discord 可用受保護 webhook 或原生 bot events。",
                    "在 `/messenger?session_name=<name>` 傳一則訊息，確認 Messenger 最終回覆同步到 Stage。",
                    "用 `/stage?session_name=<name>` 僅檢視結果畫面（字幕/TTS/Live2D）。",
                ],
            },
            {
                title: "通道與邊界",
                body: "通訊入口不是核心運行邏輯；核心是場次、角色與 runtime 控制。",
                items: [
                    "Telegram 支援 Bot API polling；Discord 支援受保護 webhook bridge，並可在開啟 Message Content Intent 後使用原生 bot events。",
                    "QQ 有 built-in adapter 入口，但尚未列入已驗證常規測試流程；LINE、WhatsApp 仍是規劃中。",
                    "Open WebUI bridge 是操作員工具介面，不是對話通道。",
                    "核心驗證都應在 `/console`、`/messenger`、`/stage` 的同場次流程中完成。",
                ],
            },
            {
                title: "Open WebUI bridge",
                body: "Open WebUI 只用來做操作員工具串接與驗證，與日常對話測試分開。",
                items: [
                    "在 `/admin/openwebui` 設定工具方法白名單與 bridge 狀態。",
                    "先完成場次流程後，再做 bridge 的工具型驗證。",
                    "聊天室測試仍以 Messenger + Stage + Console 為主。",
                ],
            },
            {
                title: "內測分享前檢查",
                body: "推送變更或把 local tunnel 開給測試者前，先完成這些檢查。",
                items: [
                    "執行 `python scripts/check_public_safety.py` 並確認通過。",
                    "執行 `git status --short`，確認 `.echobot/`、`.env`、bot token、bridge token 沒有被追蹤。",
                    "先用 `/admin/channels` 的本機 E2E 測試；真 Telegram/Discord 測試前要先收斂 allow_from。",
                    "啟用 Open WebUI tools 前，先用 `/admin/openwebui` 與 `scripts/openwebui_bridge_smoke.py` 驗證。",
                ],
            },
            {
                title: "故障判斷與第一步檢查",
                body: "行為不符合預期時，先確認場次邊界，再調整模型或通訊設定。",
                items: [
                    "Stage 沒更新：確認 Console、Messenger、Stage 使用同一場次，再刷新 `/stage?session_name=<name>`。",
                    "角色或 Live2D 沒變：中台臨時變更要按 Apply to Stage；長期綁定要到後台 Characters/Sessions 儲存。",
                    "Messenger 回覆語言不對：確認 UI 語言與角色 prompt；prompt 明確指定語言時以 prompt 優先。",
                    "Telegram/Discord 沒同步到 Stage：到 `/admin/channels` 確認 bot running、`mirror_to_stage` 已開啟，且 stage session name 正確。",
                ],
            },
            {
                title: "健康檢核",
                body: "以下都成立時，代表 場次中心操作流程已順暢。",
                items: [
                    "Console、Messenger、Stage 使用同一個場次名稱。",
                    "Messenger 回覆在 Stage 上有一致字幕與輸出。",
                    "角色與模型變更只影響到該場次上下文。",
                    "Open WebUI 僅留在操作員工具路徑，不改變一般通道驗證結果。",
                ],
            },
        ],
    },
    "zh-Hans": {
        sections: [
            {
                title: "以场次为核心的页面",
                body: "建议固定顺序：先配置资源，完成角色绑定，建立/选择场次，最后用 Console、Messenger、Stage 做联动验证。",
                items: [
                    "前台 Stage 是单一场次的显示面，展示角色、字幕、TTS 与 Live2D。",
                    "通讯 Messenger 是轻量聊天入口，按场次验证并将最终文本回传到 Stage。",
                    "中台 Console 是实时操作主控台，用于切换角色、角色卡与场次运行参数。",
                    "后台 Admin 是设置中枢，负责模型、角色、通道和文档页。",
                ],
            },
            {
                title: "推荐设置顺序",
                body: "先完成设置可减少测试波动，故障回溯也只围绕场次。",
                items: [
                    "第一步：在 `/admin/models` 配置可用的 LLM profile。",
                    "第二步：在 `/admin/voice-models` 配置 STT/TTS 语音设置。",
                    "第三步：在 `/admin/live2d` 配置 Live2D 视觉 profile。",
                    "第四步：到 `/admin/characters` 将 LLM、Voice、Live2D 绑定到同一角色配置。",
                ],
            },
            {
                title: "场次测试顺序",
                body: "完成设置后，创建一个测试场次，并通过同一场次名称做端到端验证。",
                items: [
                    "在 `/admin/sessions` 创建或选择本次测试场次。",
                    "在 `/console` 打开同一场次，并选择预先绑定的角色卡。",
                    "按需为场次选择通讯入口；Telegram 可用 polling，Discord 可用受保护 webhook 或原生 bot events。",
                    "在 `/messenger?session_name=<name>` 发一条消息，确认 Assistant 最终回复同步到 Stage。",
                    "用 `/stage?session_name=<name>` 仅验证结果输出（字幕/TTS/Live2D）。",
                ],
            },
            {
                title: "通道与边界",
                body: "通讯入口不是核心；核心是场次、角色与 runtime 控制。",
                items: [
                    "Telegram 支持 Bot API polling；Discord 支持受保护 webhook bridge，并可在开启 Message Content Intent 后使用原生 bot events。",
                    "QQ 有 built-in adapter 入口，但尚未列入已验证常规测试流程；LINE、WhatsApp 仍在规划中。",
                    "Open WebUI bridge 是操作员工具接口，不是对话通道。",
                    "核心验证仍以 `/console`、`/messenger`、`/stage` 的同场次流程为准。",
                ],
            },
            {
                title: "Open WebUI bridge",
                body: "Open WebUI 仅用于操作员工具对接和验证，和普通对话测试路径分离。",
                items: [
                    "在 `/admin/openwebui` 配置允许的工具方法与 bridge 状态。",
                    "先让场次流程稳定后，再做工具接口验证。",
                    "聊天验证仍以 Messenger + Stage + Console 为主。",
                ],
            },
            {
                title: "内测分享前检查",
                body: "推送变更或把 local tunnel 开给测试者前，先完成这些检查。",
                items: [
                    "执行 `python scripts/check_public_safety.py` 并确认通过。",
                    "执行 `git status --short`，确认 `.echobot/`、`.env`、bot token、bridge token 没有被追踪。",
                    "先用 `/admin/channels` 的本机 E2E 测试；真 Telegram/Discord 测试前要先收敛 allow_from。",
                    "启用 Open WebUI tools 前，先用 `/admin/openwebui` 与 `scripts/openwebui_bridge_smoke.py` 验证。",
                ],
            },
            {
                title: "故障判断与第一步检查",
                body: "行为不符合预期时，先确认场次边界，再调整模型或通讯设置。",
                items: [
                    "Stage 没更新：确认 Console、Messenger、Stage 使用同一场次，再刷新 `/stage?session_name=<name>`。",
                    "角色或 Live2D 没变：中台临时变更要按 Apply to Stage；长期绑定要到后台 Characters/Sessions 保存。",
                    "Messenger 回复语言不对：确认 UI 语言与角色 prompt；prompt 明确指定语言时以 prompt 优先。",
                    "Telegram/Discord 没同步到 Stage：到 `/admin/channels` 确认 bot running、`mirror_to_stage` 已开启，且 stage session name 正确。",
                ],
            },
            {
                title: "健康检核",
                body: "以下都满足时，场次中心操作流程可视为正常。",
                items: [
                    "Console、Messenger、Stage 的场次名称一致。",
                    "Messenger 回答在 Stage 上有一致字幕与输出。",
                    "角色、模型变更仅影响当前场次上下文。",
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
    appendInlineCode(body, section.body);

    const list = document.createElement("ul");
    list.className = "guide-list";
    section.items.forEach((item) => {
        const listItem = document.createElement("li");
        appendInlineCode(listItem, item);
        list.appendChild(listItem);
    });

    article.append(heading, body, list);
    return article;
}

function appendInlineCode(element, text) {
    const parts = String(text || "").split(/(`[^`]+`)/g);
    parts.forEach((part) => {
        if (!part) {
            return;
        }
        if (part.startsWith("`") && part.endsWith("`") && part.length > 1) {
            const code = document.createElement("code");
            code.textContent = part.slice(1, -1);
            element.appendChild(code);
            return;
        }
        element.appendChild(document.createTextNode(part));
    });
}

<div align="center">

<img src="./assets/banner.jpg" width="100%" alt="EchoBot Banner" />

</div>

# EchoBot Web Mobile 管理版

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> English version: [README_EN.md](./README_EN.md)

`moegundam/echobot-web-mobile` 是基於 [KdaiP/EchoBot](https://github.com/KdaiP/EchoBot) 的私有管理版，目標是把原始 EchoBot 擴充成可做本機開發、手機測試、10 人內測、Stage 展示、Messenger 通訊入口、Console 中台與 Admin 後台管理的 Web/Mobile 版本。

本專案保留 EchoBot 作為主架構，不直接合併 [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) 後端。Open-LLM-VTuber 目前只作為 Live2D、ASR/TTS、VTuber 互動體驗與桌寵式介面的參考來源。

## 專案來源與引用

| 類型 | 專案 | 本版本使用方式 |
|---|---|---|
| 上游主專案 | [KdaiP/EchoBot](https://github.com/KdaiP/EchoBot) | 本 repo 的主體來源、Agent/runtime/WebUI/Live2D/ASR/TTS/Channel 基礎 |
| 互動設計參考 | [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | 僅作 Live2D、語音互動、VTuber UX 參考，不搬整套 backend |
| 原始授權 | MIT License | 保留原始 `LICENSE`，copyright 屬於 KdaiP |

如果後續引用新的第三方專案、模型、素材或文件，必須在 README、對應文件或素材目錄中標示來源、授權與用途。

## 相對原始 EchoBot 新增的功能

### 1. Web 產品入口分層

原始 EchoBot 以 `/web` 作為主要操作頁。本版本新增並整理為多個入口：

| 頁面 | 路徑 | 用途 |
|---|---|---|
| 前台 Stage | `/stage?session_name=<name>` | 純顯示角色、字幕、TTS、Live2D lip sync |
| 通訊 Messenger | `/messenger` | 輕量聊天入口，預設 `chat_only` |
| 中台 Console | `/console` | 操作員工作台，承接原 `/web` 的完整控制能力 |
| 相容 Web | `/web` | 保留原入口，對應 Console |
| 後台 Admin | `/admin` | 後台索引、health、API docs、jobs 與管理頁入口 |
| 操作說明 | `/admin/guide` | 操作、設定、預期成果、故障判斷與排除流程 |
| 網站結構 | `/admin/structure` | Route map、Console 分區、API namespace 邊界 |
| 角色設定 | `/admin/characters` | 管理角色 prompt、模型 profile 綁定、語音、Live2D 摘要與 emotion map |
| 模型設定 | `/admin/models` | 可新增、自定義名稱、啟用角色模型 profile |
| 通訊平台 | `/admin/channels` | Telegram、QQ、LINE、Discord、WhatsApp 等 gateway 規劃入口 |
| Open WebUI Bridge | `/admin/openwebui` | Open WebUI narrow OpenAPI bridge 接線說明 |

### 2. 手機與桌面顯示模式

本版本加入語言與顯示模式控制：

- 語言：英文、繁體中文、簡體中文。
- 顯示模式：自動、手機、直向、橫向、桌面 / 密集。
- Console、Stage、Messenger、Admin 系列頁面都有一致的切換入口。
- `/console` 會依裝置與顯示模式調整手機/桌面操作版面。

### 3. 全站語言切換

本版本將原先只靠靜態 DOM 翻譯的方式，擴充到動態模組：

- ASR、TTS、sessions、roles、Live2D、trace、attachments、messages 都會跟著語言切換刷新。
- 動態按鈕、placeholder、title、aria label、狀態列與錯誤訊息不再硬編碼在功能模組內。
- 預設語言為英文，並支援繁體中文與簡體中文。

### 4. Cloudflare Local Tunnel 內測部署

新增 Local Tunnel profile，目標是先支援本機或 Mac 主機跑 EchoBot，再用 Cloudflare Tunnel + Access 提供 HTTPS 與登入。

相關文件與範本：

- [`docs/deployment/local-tunnel.md`](./docs/deployment/local-tunnel.md)
- [`docs/deployment/cloudflared-local-tunnel.example.yml`](./docs/deployment/cloudflared-local-tunnel.example.yml)
- [`.env.local-tunnel.example`](./.env.local-tunnel.example)

Local Tunnel 建議用：

```shell
python -m echobot app --host 127.0.0.1 --port 8000
```

本機測試可改 port，例如目前開發環境常用：

```shell
python -m echobot app --host 127.0.0.1 --port 8001
```

### 5. Cloudflare Access trusted-user 安全邊界

本版本新增 trusted header 模式，讓內測者資料可以依登入身份隔離：

- 預設 trusted user header：`Cf-Access-Authenticated-User-Email`
- 啟用後，受保護頁面、API docs、`/api/*` 與 ASR WebSocket 都需要可信 user id。
- session、history、jobs、attachments、settings 會寫入 `.echobot/users/<user_id>/...`。
- 不同 user 不應互看 session、history、job、attachment 或 Stage event。
- 可用 `ECHOBOT_ADMIN_ALLOWLIST` 限制 runtime、channel、role、model profile 等高風險 mutation API。

### 6. Stage Event Broker

新增 user/session scoped stage event flow：

- `GET /api/stage/events?session_name=<name>`：SSE 訂閱 Stage event。
- `POST /api/stage/events`：發布字幕與舞台事件。
- Broker v1 為 in-memory，key 包含 trusted user 與 session。
- Stage 收到 `assistant_delta` 更新字幕，收到 `assistant_final` 才做最終字幕/TTS。
- Stage event 可攜帶 `emotion`、`expression`、`motion`；`character_state` 可只更新 Live2D 表情/動作而不改字幕。
- `/admin/characters` 可為每個角色維護 emotion map；當事件只有 `emotion` 且目前 session 有綁定角色時，後端會自動補上對應的 Live2D `expression` / `motion`。

### 7. Open WebUI Bridge 接口

本版本先做好接口，不直接把 Open WebUI 接進來：

- `GET /api/openwebui/tools/openapi.json`
- `GET /api/openwebui/sessions`
- `POST /api/openwebui/stage/events`
- `POST /api/openwebui/chat`

安全設計：

- Bridge 使用 server-to-server Bearer token。
- 不暴露全站 `/openapi.json` 給 Open WebUI。
- 預設要求 `target_user_id` 或 `ECHOBOT_OPENWEBUI_BRIDGE_USER_ID`，避免寫入 shared root runtime。
- 可用 `ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS` 限制 bridge 可操作的 user namespace。
- 預設 `chat_only`。
- operator-agent mode 必須明確啟用才允許更高風險路由。

### 8. Model Profiles

新增模型 profile 管理頁：

- 預設 A-E profile。
- 使用者可持續新增 profile。
- 可自定義 profile 名稱。
- 可設定 chat、TTS、ASR、Live2D 相關 provider/model/base URL/API key。
- 啟用 profile 後，Console 會讀取並更新目前使用的模型設定。

### 9. 部署與架構文件

新增專案規劃、網站結構與參考文件：

- [`docs/implementation/echobot-web-mobile-integration-plan.md`](./docs/implementation/echobot-web-mobile-integration-plan.md)
- [`docs/implementation/echobot-web-site-structure.md`](./docs/implementation/echobot-web-site-structure.md)
- [`docs/implementation/open-llm-vtuber-reference-gap.md`](./docs/implementation/open-llm-vtuber-reference-gap.md)

## 目前狀態與公開注意事項

目前已完成：

- EchoBot 主體已整理成 Web/Mobile 管理版，並保留原 `/web` 相容入口。
- `/stage`、`/messenger`、`/console`、`/admin` 與後台說明/結構/模型/Open WebUI/channels 頁面已建立。
- 英文、繁體中文、簡體中文語言切換已套用到靜態頁面與主要動態 UI。
- 手機/平板/桌面顯示模式已加入，並驗證 360x800、390x844、430x932、768x1024 viewport 不應水平溢出。
- Cloudflare Local Tunnel、trusted-user、Stage Event Broker、Open WebUI bridge API、Model Profiles 的第一版接口與文件已建立。
- 公開前安全預設已調整為 `ECHOBOT_SHELL_SAFETY_MODE=workspace-write`。

尚未完成或仍屬規劃中的部分：

- Telegram 與 QQ 已有 built-in runtime adapter；`/admin/channels` 目前偏向狀態與規劃入口，尚未完成公開內測等級的 token/webhook 管理 UI。LINE、Discord、WhatsApp 仍屬規劃中 adapter。
- Open WebUI bridge 已有 EchoBot 端 narrow API 與說明頁，但尚未要求使用者實際接入 Open WebUI。
- `/admin` 第一版偏向索引、說明與狀態檢視，還不是完整 production SaaS 管理後台。
- Stage / Live2D / ASR / TTS 已有 v1 整合與本機 smoke；真機麥克風與長時間語音互動仍需在 HTTPS + 真機環境逐項驗收。
- 多使用者內測建議使用 Cloudflare Access 或可信 reverse proxy；不要把本地服務匿名直接暴露到公開網路。

公開 repo 代表程式碼與文件開放瀏覽，不代表這套系統已適合無保護地公開部署。部署到外網前，請先閱讀 [`SECURITY.md`](./SECURITY.md) 並啟用 trusted-user 安全邊界。

## 快速開始

### 1. 安裝依賴

建議 Python 3.11 以上。

```shell
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 建立設定檔

```shell
cp .env.example .env
```

常用 OpenAI-compatible 設定：

```text
LLM_API_KEY=your_api_key_here
LLM_MODEL=your-model-name
LLM_BASE_URL=https://your-provider.example/v1
```

本地模型、遠端私有模型服務與 API key 請在自己的 `.env` 或 secret manager 中設定，不要把實際主機、tailnet IP、模型清單或 key 放進公開 repo。

### 3. 啟動本機服務

```shell
python -m echobot app --host 127.0.0.1 --port 8000
```

開發時若 8000 被占用，可改用：

```shell
python -m echobot app --host 127.0.0.1 --port 8001
```

### 4. 開啟頁面

```text
http://127.0.0.1:8000/console
http://127.0.0.1:8000/stage?session_name=demo
http://127.0.0.1:8000/messenger
http://127.0.0.1:8000/admin
```

## 測試

```shell
python -m pytest
```

目前本分支驗證過：

- 全站 10 個 route × 手機/桌面 × 3 語言瀏覽器檢查。
- i18n key coverage。
- API route/auth tests。
- full pytest：`312 passed`。

## 專案規矩

1. 保留上游 EchoBot 的 MIT License 與 copyright。
2. README、文件或素材若引用第三方來源，必須標註來源、授權與用途。
3. Secrets 不進 repo，包括 LLM key、Cloudflare token、Open WebUI bridge token、通訊平台 bot token。
4. 內測部署先使用 Cloudflare Access 或可信 reverse proxy，不做匿名公開。
5. `/messenger` 與外部通訊 gateway 預設 `chat_only`，工具型 Agent 權限需另設 approval gate。
6. user data 預設寫入 `.echobot/users/<user_id>/...`，不可跨 user 混用。
7. 新增頁面時要同步支援英文、繁體中文、簡體中文。
8. 重大功能需補文件與測試，至少保留可重跑的最小驗證。

## License

本專案沿用上游 EchoBot 的 MIT License。請見 [`LICENSE`](./LICENSE)。

原始 copyright：

```text
Copyright (c) 2026 KdaiP
```

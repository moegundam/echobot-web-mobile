<div align="center">

<img src="./assets/banner.jpg" width="100%" alt="EchoBot Banner" />

</div>

# EchoBot Web Mobile 管理版

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> English version: [README_EN.md](./README_EN.md)

`moegundam/echobot-web-mobile` 是在 [KdaiP/EchoBot](https://github.com/KdaiP/EchoBot) 基礎上重整出的 Web/Mobile 管理版。這不是單純換皮：本 fork 把原本偏單一 `/web` 操作面的 EchoBot，改成可做本機開發、手機測試、10 人內測、Stage 展示、Messenger 通訊入口、Console 中台與 Admin 後台管理的版本。

## 本 fork 改了多少

以目前可驗證的頁面、API、測試、文件與 smoke script 來計算，本 fork 相對原始 EchoBot 已新增或重構 **12 個功能群組**，並修正/收斂 **9 類公開前會影響使用與安全的問題**。這裡用的是「功能群組」計算，不是 commit 數、逐行 diff 或單一按鈕數量。

### 新增或重構的 12 個功能群組

| # | 功能群組 | 說明 |
|---:|---|---|
| 1 | Stage 前台 | `/stage` 變成正式互動顯示面，負責角色、字幕、TTS、Live2D 與舞台狀態 |
| 2 | Messenger 通訊入口 | `/messenger` 作為內部 Web Chat，可依 Session 繼續對話，不需要手動輸入平台 bot |
| 3 | Console 中台 | `/console` 作為操作員工作台，保留 `/web` 相容入口並補跨頁導覽 |
| 4 | Admin 後台 | `/admin` 拆出 guide、structure、deployment、models、voice、Live2D、characters、channels 等頁面 |
| 5 | Session-centered runtime | 以 Session 為核心，把角色、模型、語音、Live2D、通訊入口與 conversation state 串起來 |
| 6 | 三語 i18n | 英文、繁體中文、簡體中文切換，涵蓋主要靜態與動態 UI |
| 7 | 裝置/顯示模式 | 加入自動、手機、直向、橫向、桌面/密集等模式，修正手機和平板顯示 |
| 8 | Trusted-user namespace | Cloudflare Access / reverse proxy trusted header 模式與 `.echobot/users/<user_id>` 隔離 |
| 9 | Stage Event Broker | user/session scoped SSE event broker，支援字幕、emotion、expression、motion 與 Stage replay |
| 10 | Runtime profiles | LLM、Voice、Live2D 分頁管理，角色可綁定完整互動配置並匯入/匯出 package |
| 11 | Channel gateways | Telegram/Discord 設定、smoke、stage target projection 與 deterministic `/ping` 驗證入口 |
| 12 | Open WebUI / 部署 / CI | Narrow OpenAPI bridge、Docker package、deployment readiness、public safety scan、browser smoke、CI 驗證 |

### 修正/收斂的 9 類問題

| # | 類型 | 已處理方向 |
|---:|---|---|
| 1 | 公開資訊外洩 | `/api/health` 不再輸出本機絕對路徑，README 避免放私有主機或 token |
| 2 | Secret 顯示與儲存 | API key、bot token、bridge token、webhook secret 僅顯示 configured 狀態；channel credentials 不再寫入 `channels.json` |
| 3 | 中台/後台責任混亂 | 後台負責持久設定；中台負責測試與臨時 runtime override，並可套用到前台 |
| 4 | 模型設定混在一起 | `/admin/models` 限縮為 LLM；Voice 與 Live2D 拆到專頁 |
| 5 | 硬編碼語言 | 主要按鈕、placeholder、狀態、動態文案納入 i18n |
| 6 | Session/平台概念混亂 | 使用者主要選 Session；Channel 只是入口與 metadata，不當核心邏輯 |
| 7 | 手機/桌面版面問題 | 修正 360/390/430/768 viewport 與桌面雙欄操作面 |
| 8 | Gateway 測試不穩 | 加入 `/ping` / `/smoke` deterministic command，避免 E2E 依賴 LLM 精準回覆 |
| 9 | 公開前驗證不足 | 加入 public safety scan、browser smoke、targeted tests 與 GitHub Actions 狀態檢查 |

## 截圖

| Admin 後台 | 網站結構 |
|---|---|
| ![Admin overview](./docs/assets/screenshots/admin-overview.png) | ![Site structure](./docs/assets/screenshots/site-structure.png) |
| 操作說明 | 手機 Stage |
| ![Operation guide](./docs/assets/screenshots/operation-guide.png) | ![Mobile Stage](./docs/assets/screenshots/stage-mobile.png) |

## 上游來源與引用

| 類型 | 專案 | 本版本使用方式 |
|---|---|---|
| 上游主專案 | [KdaiP/EchoBot](https://github.com/KdaiP/EchoBot) | 本 repo 的主體來源、Agent/runtime/WebUI/Live2D/ASR/TTS/Channel 基礎 |
| 互動設計參考 | [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | 僅作 Live2D、語音互動、VTuber UX 參考，不搬整套 backend |
| 原始授權 | MIT License | 保留原始 `LICENSE`；原始 copyright 屬於 KdaiP，本 fork 的新增修改由 `moegundam` 維護 |

如果後續引用新的第三方專案、模型、素材或文件，必須在 README、對應文件或素材目錄中標示來源、授權與用途。

本專案保留 EchoBot 作為主架構，不直接合併 [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) 後端。Open-LLM-VTuber 目前只作為 Live2D、ASR/TTS、VTuber 互動體驗與桌寵式介面的參考來源。

## 功能細節

### 1. Web 產品入口分層

原始 EchoBot 以 `/web` 作為主要操作頁。本版本新增並整理為多個入口：

| 頁面 | 路徑 | 用途 |
|---|---|---|
| 前台 Stage | `/stage?session_name=<name>` | 純顯示角色、字幕、TTS、Live2D lip sync；可從已設定通訊平台選擇 target |
| 通訊 Messenger | `/messenger` | 輕量聊天入口，預設 `chat_only`；可選 Telegram/Discord 等已設定 target，不必手動輸入 session |
| 中台 Console | `/console` | 操作員工作台，承接原 `/web` 的完整控制能力 |
| 相容 Web | `/web` | 保留原入口，對應 Console |
| 後台 Admin | `/admin` | 後台索引、health、API docs、jobs 與管理頁入口 |
| 操作說明 | `/admin/guide` | 操作、設定、預期成果、故障判斷與排除流程 |
| 網站結構 | `/admin/structure` | Route map、Console 分區、API namespace 邊界 |
| Sessions | `/admin/sessions` | 建立、檢視與維護 Session；Session 是角色、模型、通訊入口與對話狀態的核心 |
| 角色設定 | `/admin/characters` | 管理角色 prompt、LLM / Voice / Live2D 綁定、emotion map 與角色 package 匯入/匯出 |
| LLM 模型 | `/admin/models` | 管理 LLM provider、model、base URL、API key 與推理參數 |
| 語音模型 | `/admin/voice-models` | 管理 STT/TTS provider、voice、language 與語音 profile |
| Live2D | `/admin/live2d` | 管理 Live2D 選擇、asset catalog 與視覺 profile |
| 通訊平台 | `/admin/channels` | Telegram / Discord 設定與 smoke 驗證，QQ/LINE/WhatsApp 等 gateway 管理入口 |
| Open WebUI Bridge | `/admin/openwebui` | Open WebUI narrow OpenAPI bridge 接線說明 |
| 部署檢查 | `/admin/deployment` | 本機服務、Cloudflare、GitHub Actions 與 Open WebUI bridge readiness 檢查 |

### 2. 手機與桌面顯示模式

本版本加入語言與顯示模式控制：

- 語言：英文、繁體中文、簡體中文。
- 顯示模式：自動、手機、直向、橫向、桌面 / 密集。
- Console、Stage、Messenger、Admin 系列頁面都有一致的切換入口。
- `/console` 會依裝置與顯示模式調整手機/桌面操作版面。

### 3. 全站語言切換

本版本將原先只靠靜態 DOM 翻譯的方式，擴充到動態模組：

- ASR、TTS、sessions、roles、Live2D、trace、attachments、messages 都會跟著語言切換刷新。
- 主要動態按鈕、placeholder、title、aria label、狀態列與錯誤訊息已納入 i18n 管理，後續新增 UI 應延續同一模式。
- 預設語言為英文，並支援繁體中文與簡體中文。

### 4. Cloudflare Local Tunnel 內測部署

新增 Local Tunnel profile，目標是先支援本機或 Mac 主機跑 EchoBot，再用 Cloudflare Tunnel + Access 提供 HTTPS 與登入。

相關文件與範本：

- [`docs/deployment/local-tunnel.md`](./docs/deployment/local-tunnel.md)
- [`docs/deployment/docker.md`](./docs/deployment/docker.md)
- [`docs/deployment/openwebui-stable-entry.md`](./docs/deployment/openwebui-stable-entry.md)
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
- 可用 `ECHOBOT_ADMIN_ALLOWLIST` 限制 runtime、channel、role、LLM/voice/Live2D profile 等高風險 mutation API。

### 6. Stage Event Broker

新增 user/session scoped stage event flow：

- `GET /api/stage/events?session_name=<name>`：SSE 訂閱 Stage event。
- `POST /api/stage/events`：發布字幕與舞台事件。
- 目前 app runtime 預設使用 bounded in-memory broker，key 包含 trusted user 與 session，並支援 `Last-Event-ID` cursor replay。
- 已提供 Redis Streams adapter foundation：每個 user/session 使用獨立雜湊 key、各自保留上限與 TTL；尚未接成預設 runtime，也尚未完成真 Redis 跨 process 驗收。
- Stage 收到 `assistant_delta` 更新字幕，收到 `assistant_final` 才做最終字幕/TTS。
- Stage event 可攜帶 `emotion`、`expression`、`motion`；`character_state` 可只更新 Live2D 表情/動作而不改字幕。
- `/admin/characters` 可為每個角色維護 emotion map；當事件只有 `emotion` 且目前 session 有綁定角色時，後端會自動補上對應的 Live2D `expression` / `motion`。

### 7. Open WebUI Bridge 接口

本版本已做好 EchoBot 端窄化接口與本機 smoke；要讓外部 Open WebUI 呼叫，需另外設定 bridge token 與可信網路入口：

- `GET /api/openwebui/tools/openapi.json`
- `GET /api/openwebui/sessions`
- `POST /api/openwebui/stage/events`
- `POST /api/openwebui/chat`

安全設計：

- Bridge 使用 server-to-server Bearer token。
- 不暴露全站 `/openapi.json` 給 Open WebUI。
- 預設要求 `target_user_id` 或 `ECHOBOT_OPENWEBUI_BRIDGE_USER_ID`，避免寫入 shared root runtime。
- 必須用 `ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS` 明確列出 bridge 可操作的 user namespace；空白 allowlist 會 fail closed 並拒絕所有具名 target。
- 預設 `chat_only`。
- operator-agent mode 必須明確啟用才允許更高風險路由。

### 8. Runtime Profiles：LLM、Voice、Live2D 分頁

本版本把角色 runtime 需要的模型設定拆成三個後台頁面，避免所有設定塞在同一個 profile 造成操作混亂：

- `/admin/models`：只管理 LLM / chat model provider、model、base URL、API key 與推理參數。
- `/admin/voice-models`：管理 STT/TTS provider、model、voice、language、base URL 與 API key。
- `/admin/live2d`：管理 Live2D selection、可用 catalog 與視覺 profile。
- `/admin/characters`：把 LLM、Voice、Live2D 綁到角色，形成完整互動單位。
- `/console`：可針對目前 session 做臨時 runtime override；中台變更不會覆寫後台 profile，但可套用到前台 Stage。

### 9. Character Packages

`/admin/characters` 可匯出與匯入單一角色 package：

- 匯出內容包含角色 prompt、LLM / Voice / Live2D 綁定、emotion map 與非敏感模型設定快照。
- 匯出內容不包含 API key、bot token、Cloudflare/Open WebUI token 或 `.echobot/` secret。
- 匯入時可指定新角色名稱，也可選擇覆蓋既有角色。
- v1 使用 JSON package，不打包 Live2D asset 檔案；模型 API key 仍需在 `/admin/models` 補填。

### 10. Channels 管理頁

`/admin/channels` 已從只讀規劃頁升級為通訊平台設定入口：

- Telegram 可設定 enabled、allow list、bot token、proxy、reply-to-message 與啟動時是否丟棄 pending updates。
- Discord 可設定 enabled、allow list、bot token、webhook URL、webhook secret、application/guild/channel id；目前支援受 secret 保護的 `POST /api/channels/discord/webhook` inbound bridge、outbound webhook 發送，以及安裝 `discord.py` 並開啟 Message Content Intent 後的原生 Discord bot events。
- Secret 欄位在 API 與 UI 中只顯示 configured 狀態，不回傳明文。Telegram、Discord、QQ credentials 儲存在 repo 外的 `.echobot/channel_secrets.json`（`0600`）；舊 `channels.json` inline secret 會在下一次儲存時遷移。
- 儲存 enabled channel 時會先等待 adapter 回報 ready；啟用失敗回傳去敏感的 `409`，不覆寫磁碟設定，並恢復原本仍可用的 runtime。
- `POST /api/channels/{channel}/smoke` 提供安全的本機 readiness check，不會把 token 回傳到 response。
- `scripts/telegram_gateway_smoke.py` 與 `scripts/discord_gateway_smoke.py` 可重跑 gateway 檢查；一般文字會驗證 session history，`/ping` / `/smoke` deterministic command 會改驗證 Stage replay，因為這類 command 不寫入一般對話 history。
- `GET /api/channels/stage-targets` 提供無 secret 的通訊 target 清單，讓 `/stage` 與 `/messenger` 直接選擇已設定平台綁定的前台 session。
- Telegram Bot API `getMe`、poller 啟動、Bot API outbound、session 綁定與 Stage target projection 已有可重跑 smoke path；實際 bot token 必須放在 repo 外的 ignored runtime config。
- 正式通訊 gateway 可設定 `mirror_to_stage` 與 `stage_session_name`；Telegram 曾有維護者環境 inbound/Stage 歷史 smoke，但每次部署仍需重新執行外部 E2E 才能宣稱通過。
- Discord webhook bridge 可接收受 secret 保護的 inbound request，原生 Discord bot events adapter 也已完成；Discord 曾有維護者環境歷史 smoke，但正式環境仍需 repo 外 bot token、Message Content Intent 與本次部署的 fresh E2E。
- 通訊 gateway 內建 `/ping <text>` / `/smoke <text>` deterministic smoke command，避免平台 E2E 測試依賴 LLM 是否剛好遵守「精確回覆」提示。

### 11. 部署與架構文件

新增專案規劃、網站結構與參考文件：

- [`docs/implementation/echobot-web-mobile-integration-plan.md`](./docs/implementation/echobot-web-mobile-integration-plan.md)
- [`docs/implementation/echobot-web-page-links.md`](./docs/implementation/echobot-web-page-links.md)
- [`docs/implementation/echobot-web-site-structure.md`](./docs/implementation/echobot-web-site-structure.md)
- [`docs/implementation/open-llm-vtuber-reference-gap.md`](./docs/implementation/open-llm-vtuber-reference-gap.md)

## 目前狀態與公開注意事項

目前已完成：

- EchoBot 主體已整理成 Web/Mobile 管理版，並保留原 `/web` 相容入口。
- `/stage`、`/messenger`、`/console`、`/admin` 與後台說明/結構/模型/Open WebUI/channels 頁面已建立。
- 英文、繁體中文、簡體中文語言切換已套用到靜態頁面與主要動態 UI。
- 手機/平板/桌面顯示模式已加入，並驗證 360x800、390x844、430x932、768x1024 viewport 不應水平溢出。
- Cloudflare Local Tunnel、trusted-user、Stage Event Broker、Open WebUI bridge API、LLM / Voice / Live2D profiles、Character Packages 與 Channels 設定/smoke 的第一版接口與文件已建立。
- Telegram / Discord 有歷史維護者 smoke，Voice TTS/ASR 與 Open WebUI bridge 有本機/歷史整合證據；這些不等於目前部署的 fresh external acceptance。
- Console/Admin UX 已補強：route mode 不再顯示 raw enum、Messenger 讀取場次 route mode、Stage/Messenger 補跨頁導覽、Open WebUI/Channels 顯示可重跑入口與平台實測狀態。
- 公開前安全預設已調整為 `ECHOBOT_SHELL_SAFETY_MODE=workspace-write`。
- Compose 已使用 loopback Nginx ingress，app port 只在容器網路內可見；ingress 先執行 request-size、rate 與 stream connection 限制，並以 Docker DNS 動態重解析 app 位址與 HTTP live healthcheck 驗證實際服務。
- Runtime/dev dependencies 使用 hash-enforced lock；CI 對 Python dependencies、EchoBot app image 與 Nginx ingress image 分別保存 SBOM/Trivy evidence，並為 app image 產生 provenance/attestation。是否完成發布仍以當次 GitHub Actions 為準。

尚未完成或仍屬規劃中的部分：

- LINE、WhatsApp 正式 runtime adapter 仍屬規劃中；QQ adapter 已保留 built-in 入口但尚未做真實平台長跑驗證。
- Open WebUI bridge 已有 EchoBot 端 narrow API、說明頁與本機 smoke script；過往維護環境有 reverse-tunnel 驗證紀錄，但每個新部署仍必須重跑 tool spec、Stage、chat 與權限 E2E。Cloudflare Tunnel / Access 仍是正式 HTTPS 入口。
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

### 模型與 CUDA 部署策略

EchoBot 的 Docker image 預設是輕量 app runtime，不打包 LLM 權重或 CUDA runtime。若要用 GB10、LiteLLM、Ollama、vLLM 或其他 GPU provider，建議讓那些服務獨立執行，再用 OpenAI-compatible endpoint 接到 EchoBot；EchoBot 專注管理 session、角色、Stage、Messenger、Console、Admin 與 channel gateway。

### 3. 啟動本機服務

```shell
python -m echobot app --host 127.0.0.1 --port 8000
```

開發時若 8000 被占用，可改用：

```shell
python -m echobot app --host 127.0.0.1 --port 8001
```

### Docker / Compose 啟動

本版本提供 `Nginx ingress + EchoBot app` 的 Compose 打包。請在指定 Docker host（本維護流程使用外部 Mac mini Docker server）執行；一般工作站不需要啟動 Docker daemon：

```shell
cp docker.env.example docker.env.local
docker compose build
docker compose up -d
curl -fsS http://127.0.0.1:8080/healthz
```

App container 的 `8000` 只在 Compose network 內可見；瀏覽器、Cloudflare Tunnel 與 health smoke 都走 loopback ingress `127.0.0.1:8080`。

正式部署應使用 GitHub Container Registry 的 digest-qualified image：

```text
ghcr.io/moegundam/echobot-web-mobile@sha256:<digest>
```

詳細說明請見 [`docs/deployment/docker.md`](./docs/deployment/docker.md)、[`docs/security/secret-storage.md`](./docs/security/secret-storage.md) 與 [`docs/architecture/stage-event-broker.md`](./docs/architecture/stage-event-broker.md)。

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

目前本分支的可重跑驗證包含：

- 主要 route 的手機/平板/桌面 browser smoke。
- i18n key coverage 與 HTML translatable attribute 檢查。
- API route/auth tests。
- browser smoke：`scripts/browser_smoke.py --base-url http://127.0.0.1:8001`。
- public safety scan：`scripts/check_public_safety.py`。
- full pytest / CI：以當次 GitHub Actions 與 release evidence 為準，不在 README 固定會過期的測試數字。

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

本專案沿用 MIT License。請見 [`LICENSE`](./LICENSE)。上游 EchoBot copyright 保留為 KdaiP，本 fork 的新增修改以 `moegundam` 名義標示在同一份 MIT 授權中。

授權標示：

```text
Copyright (c) 2026 KdaiP
Additional modifications Copyright (c) 2026 moegundam
```

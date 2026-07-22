# EchoBot Web Site Structure

## 中文版

### 目的

建立一套以 Session 為核心的操作理解：先完成資源設定，再綁定角色，最後透過 `Console`、`Messenger`、`Stage` 做 session 測試。`Channels` 只負責進入口，不是核心控制面；Open WebUI bridge 是操作員工具接口。

### Session 流程

1. Admin 設定 LLM：到 `/admin/models` 建立可用的 LLM profile。
2. Admin 設定 Voice：到 `/admin/voice-models` 建立 STT/TTS profile。
3. Admin 設定 Live2D：到 `/admin/live2d` 建立視覺 profile。
4. Admin 角色綁定：到 `/admin/characters` 將 LLM/Voice/Live2D 綁到同一角色設定。
5. Session 測試：到 `/admin/sessions` 建立/選擇 session，接著到 `/console` 選角色與可選 channel，最後用 `/messenger?session_name=<name>` 與 `/stage?session_name=<name>` 驗證。
6. 通道狀態確認：`/admin/channels` 僅做入口管理，Telegram / Discord 為目前可重跑 smoke 的通道；QQ 保留 adapter 入口但尚未列入常規實測；LINE、WhatsApp 仍規劃中。
7. Open WebUI bridge：在 `/admin/openwebui` 僅作為操作員工具接口設定與狀態檢視。

### 第一層頁面

| 層級 | Route | 頁面責任 | 不應承擔 |
|---|---|---|---|
| 前台 | `/stage?session_name=<name>` | 單一 session 的角色顯示、字幕、TTS、Live2D lip sync（結果輸出） | 不做即時模型/角色控制 |
| 通訊 | `/messenger?session_name=<name>` | 輕量聊天輸入；將最終回覆同步到 Stage | 不承擔 Console 的即時控制 |
| 說明 | `/guide` | 依登入角色顯示可用頁面、首次成功流程、名詞與故障排除 | 不提供 Admin mutation 權限 |
| 中台 | `/console` | 會話層即時操作台：角色卡、模型、語音、Live2D、runtime 切換 | 不放設計文件與長期設定索引 |
| 後台 | `/admin` | 受保護入口：模型/語音/Live2D、角色、通道、文件與設置 | 不做即時對話控制 |

### 存取角色

| 角色 | 可用入口 | 不可用範圍 |
|---|---|---|
| Admin | 全部頁面與 API（含 `/guide`） | 無；仍受 secrets、proxy 與 runtime safety policy 約束 |
| Operator | `/guide`、`/web`、`/console`、`/messenger`、`/stage`；自己的 Session 與暫時 runtime override | `/admin*`、secrets、provider endpoint、Channel/部署管理、持久素材上傳、Agent route |
| User | `/guide`、`/messenger`、`/stage` 與自己的 Session 對話資料 | Console、Admin 與 owner-global API |

`ECHOBOT_ADMIN_ALLOWLIST` 與 `ECHOBOT_OPERATOR_ALLOWLIST` 分開設定。Admin 同時具備 Operator 能力；同一使用者出現在兩個清單時，以 Admin 為準。
非 Admin 呼叫 Web config、Session runtime context 或 health 時，回應會移除 provider endpoint、API key 狀態、本機 ASR 資源路徑、Channel/bus 狀態與全域 runtime 設定。
`POST /api/stage/events` 刻意允許已驗證的 User 使用，因 Messenger 需把該使用者自己 Session 的字幕同步到 Stage；broker 仍以 user/session 隔離並限制事件大小與佇列容量。

### `/console` 內部

| 分區 | 內容 | 目的 |
|---|---|---|
| Session panel | 連線狀態、session badge、角色/模型狀態、語言、Live2D 顯示 | 讓操作員看到會話目前狀態 |
| Control drawers | session 清單、角色卡選擇 | 切換當前會話控制上下文 |
| Settings groups | chat-only route、TTS、Live2D 與 Stage 暫時覆寫；全域 runtime、ASR provider、CRON、HEARTBEAT 只對 Admin 顯示 | 控制當前 session，且不寫回 Admin profile |
| Conversation area | transcript、attachments、麥克風、發送 | 驗證 session 內訊息流程 |

### Admin 子頁面

| Route | 類型 | 責任 |
|---|---|---|
| `/admin/structure` | 架構文件 | 頁面地圖、Console 分區、API namespace |
| `/admin/guide` | 操作說明 | Session 流程與對應檢核 |
| `/admin/sessions` | 會話維運 | 會話建立/重命名/刪除與進入 Console |
| `/admin/models` | 模型設定 | LLM profile 管理 |
| `/admin/voice-models` | 語音設定 | STT/TTS profile 管理 |
| `/admin/live2d` | 視覺設定 | Live2D 目錄與視覺 profile 管理 |
| `/admin/characters` | 角色設定 | 角色綁定 LLM/Voice/Live2D |
| `/admin/channels` | 通道入口 | Telegram/Discord 設定與 smoke；QQ adapter 入口；LINE/WhatsApp 規劃中 |
| `/admin/openwebui` | 工具接口 | Open WebUI bridge 接線與工具白名單 |
| `/admin/deployment` | 部署檢查 | 本機服務、Cloudflare、GitHub Actions 與 Open WebUI bridge readiness |

### API 分組

| Namespace | 對應頁面 | 職責 |
|---|---|---|
| `/api/web/*` | `/console` | Web config、runtime、Live2D、TTS、ASR、WebSocket |
| `GET /api/access` | `/guide`、`/stage`、`/messenger` | 只回傳 role 與 Console/Admin/Agent capability；不回傳 allowlist、identity header 或 secret |
| `/api/chat*` | `/console`、`/messenger` | 對話、stream、jobs、trace |
| `/api/sessions*` | `/console`、`/messenger`、`/stage` | session lifecycle 與當前 session |
| `PUT /api/sessions/{session_name}/configuration` | `/console` | Operator/Admin 更新該 Session 的暫時角色、LLM、Voice、Live2D 或 Channel runtime；不覆寫後台 profile |
| `/api/stage/events` | `/stage`、`/messenger` | session-scoped 字幕與舞台事件推送 |
| `/api/character-profiles*` | `/admin/characters` | 角色定義、prompt、角色綁定 |
| `/api/llm-models` | `/admin/models` | LLM profile 管理 |
| `/api/voice-models` | `/admin/voice-models` | STT/TTS profile 管理 |
| `/api/live2d-models` | `/admin/live2d` | Live2D profile 管理 |
| `/api/model-profiles*` | 相容層 | 舊 model profile 相容投影；新 UI 應優先使用 split model APIs |
| `/api/openwebui/*` | `/admin/openwebui`、Open WebUI | 操作員工具 API bridge |
| `/api/channels/*` | `/admin/channels` | 通道設定、狀態與 smoke 準備 |
| `/api/deployment/status` | `/admin/deployment` | 唯讀部署 readiness 與建議命令 |
| `/api/roles*`、`/api/attachments*`、`/api/cron*`、`/api/heartbeat*` | `/console` | 角色卡、檔案、排程、HEARTBEAT |

### 規則

- Session-based 操作保持 `/admin`（設定）與 `/console`（即時操作）分離；`Messenger`/`Stage`僅作消息入口與輸出。
- 通道是進入口，不是核心流程；先用 Telegram/Discord 驗證，QQ 保留 adapter 入口，LINE/WhatsApp 暫停在規劃清單。
- Open WebUI bridge 只在需要工具接口時使用，與一般會話測試路徑分離。

### Site Map

```mermaid
flowchart TD
    Root["/ API identity"] --> Docs["/docs /redoc /openapi.json"]
    Root --> Console["/console"]
    Root --> WebAlias["/web legacy alias"]
    Root --> Stage["/stage"]
    Root --> Messenger["/messenger"]
    Root --> Admin["/admin"]

    Admin --> Structure["/admin/structure"]
    Admin --> Guide["/admin/guide"]
    Admin --> Sessions["/admin/sessions"]
    Admin --> Models["/admin/models"]
    Admin --> Voice["/admin/voice-models"]
    Admin --> Live2D["/admin/live2d"]
    Admin --> Characters["/admin/characters"]
    Admin --> Channels["/admin/channels"]
    Admin --> OpenWebUI["/admin/openwebui"]
    Admin --> Deployment["/admin/deployment"]

    Console --> WebAPI["/api/web/*"]
    Console --> ChatAPI["/api/chat* /api/sessions* /api/roles*"]
    Messenger --> ChatAPI
    Stage --> StageAPI["/api/stage/events SSE"]
    Characters --> CharacterAPI["/api/character-profiles*"]
    Models --> ModelAPI["/api/llm-models"]
    Voice --> VoiceAPI["/api/voice-models"]
    Live2D --> Live2DAPI["/api/live2d-models"]
    OpenWebUI --> BridgeAPI["/api/openwebui/*"]
    Deployment --> DeployAPI["/api/deployment/status"]
```

## English version

### Purpose

Define a session-centered operation flow: set up resources first, bind them into a character, then test with `Console`, `Messenger`, and `Stage`. Channels are entry points, not the core control path. Open WebUI bridge is an operator tool interface.

### Session flow

1. Configure LLM in `/admin/models`.
2. Configure voice settings in `/admin/voice-models`.
3. Configure Live2D in `/admin/live2d`.
4. In `/admin/characters`, bind LLM profile + voice profile + Live2D profile into one character.
5. Create/select a session in `/admin/sessions`, choose role and optional channel in `/console`, then validate through `/messenger?session_name=<name>` and `/stage?session_name=<name>`.
6. Channel status is managed in `/admin/channels`: Telegram and Discord have repeatable smoke paths; QQ keeps an adapter entry but is not in the regular verified path yet; LINE and WhatsApp remain planned.
7. Use `/admin/openwebui` only as the operator tool interface for bridge setup and status.

### Top-Level Pages

| Layer | Route | Responsibility | Should not do |
|---|---|---|---|
| Front display | `/stage?session_name=<name>` | Single-session output: character, subtitles, TTS, and Live2D lip sync | No live model/character controls |
| Communication | `/messenger?session_name=<name>` | Lightweight input path; publishes final assistant output to Stage | No runtime control |
| Guidance | `/guide` | Role-aware pages, first-success flow, glossary, and troubleshooting | Grants no Admin mutation capability |
| Operator console | `/console` | Session-centered live control: role card, model, voice, Live2D, and runtime toggles | Not a docs/config index |
| Admin | `/admin` | Protected hub for setup pages and documentation | Not live session control |

### Access Roles

| Role | Available surfaces | Restricted surfaces |
|---|---|---|
| Admin | All pages and APIs, including `/guide` | None beyond secret, proxy, and runtime safety policies |
| Operator | `/guide`, `/web`, `/console`, `/messenger`, `/stage`, own sessions, and temporary runtime overrides | `/admin*`, secrets, provider endpoints, channel/deployment management, persistent asset uploads, and Agent routes |
| User | `/guide`, `/messenger`, `/stage`, and own session conversation data | Console, Admin, and owner-global APIs |

Configure `ECHOBOT_ADMIN_ALLOWLIST` and `ECHOBOT_OPERATOR_ALLOWLIST` separately. Admins inherit Operator capabilities; when an identity appears in both lists, Admin wins.
For non-Admin callers, Web config, Session runtime-context, and health responses omit provider endpoints, API-key status, local ASR resource paths, Channel/bus status, and global runtime settings.
`POST /api/stage/events` intentionally remains available to authenticated Users because Messenger must synchronize subtitles for that User's own Session to Stage. The broker remains user/session scoped with bounded event and queue sizes.

### `/console` Internal Sections

| Section | Content | Purpose |
|---|---|---|
| Session panel | connection state, session badge, character/model status, language, Live2D view | View active session state |
| Control drawers | session list and character card selection | Keep current session context |
| Settings groups | chat-only routing, TTS, Live2D, and temporary Stage overrides; global runtime, ASR provider, CRON, and HEARTBEAT remain Admin-only | Control the current session without overwriting Admin profiles |
| Conversation area | transcript, attachments, mic, send controls | Run and inspect session messages |

### Admin Child Pages

| Route | Type | Responsibility |
|---|---|---|
| `/admin/structure` | Information architecture | Page map, Console sections, API namespace grouping |
| `/admin/guide` | Runbook | Session flow and operation reference |
| `/admin/sessions` | Session maintenance | Create, rename, delete, and open-in-console checks |
| `/admin/models` | LLM setup | LLM profile management |
| `/admin/voice-models` | Speech setup | STT/TTS profile management |
| `/admin/live2d` | Visual setup | Live2D catalog and profile management |
| `/admin/characters` | Character setup | Bind LLM, voice, and Live2D into one character |
| `/admin/channels` | Channel entrypoints | Telegram/Discord setup and smoke checks; QQ adapter entry; LINE/WhatsApp planned |
| `/admin/openwebui` | Tool bridge | Open WebUI interface status and operator tool wiring |
| `/admin/deployment` | Deployment readiness | Local service, Cloudflare, GitHub Actions, and Open WebUI bridge readiness |

### API Groups

| Namespace | Page | Responsibility |
|---|---|---|
| `/api/web/*` | `/console` | Web config, runtime, Live2D, TTS, ASR, WebSocket |
| `GET /api/access` | `/guide`, `/stage`, `/messenger` | Returns only role and Console/Admin/Agent capabilities; never allowlists, identity headers, or secrets |
| `/api/chat*` | `/console`, `/messenger` | chat, stream, jobs, trace |
| `/api/sessions*` | `/console`, `/messenger`, `/stage` | session lifecycle and current session |
| `PUT /api/sessions/{session_name}/configuration` | `/console` | Operator/Admin updates temporary character, LLM, Voice, Live2D, or Channel runtime for that Session without overwriting Admin profiles |
| `/api/stage/events` | `/stage`, `/messenger` | user/session-scoped stage subtitle and event publishing |
| `/api/character-profiles*` | `/admin/characters` | character definition and bindings |
| `/api/llm-models` | `/admin/models` | LLM profile management |
| `/api/voice-models` | `/admin/voice-models` | STT/TTS profile management |
| `/api/live2d-models` | `/admin/live2d` | Live2D profile management |
| `/api/model-profiles*` | Compatibility layer | Legacy model-profile projection; new UI should prefer split model APIs |
| `/api/openwebui/*` | `/admin/openwebui`, Open WebUI | Operator tool bridge endpoint |
| `/api/channels/*` | `/admin/channels` | channel settings, status, and smoke readiness |
| `/api/deployment/status` | `/admin/deployment` | Read-only deployment readiness and recommended commands |
| `/api/roles*`, `/api/attachments*`, `/api/cron*`, `/api/heartbeat*` | `/console` | roles, files, schedules, heartbeat |

### Route rules

- Keep Admin (setup) and Console (live operation) separate; use Messenger/Stage only for input and output checks.
- Channels are entry points, not the control core. Use Telegram/Discord for current tests; keep QQ adapter-only until real-platform verification, and keep LINE/WhatsApp in the roadmap.
- Open WebUI bridge is for operator tool actions and should be tested separately from normal session-path checks.

### Site Map

```mermaid
flowchart TD
    Root["/ API identity"] --> Docs["/docs /redoc /openapi.json"]
    Root --> Console["/console"]
    Root --> WebAlias["/web legacy alias"]
    Root --> Stage["/stage"]
    Root --> Messenger["/messenger"]
    Root --> Admin["/admin"]

    Admin --> Structure["/admin/structure"]
    Admin --> Guide["/admin/guide"]
    Admin --> Sessions["/admin/sessions"]
    Admin --> Models["/admin/models"]
    Admin --> Voice["/admin/voice-models"]
    Admin --> Live2D["/admin/live2d"]
    Admin --> Characters["/admin/characters"]
    Admin --> Channels["/admin/channels"]
    Admin --> OpenWebUI["/admin/openwebui"]
    Admin --> Deployment["/admin/deployment"]

    Console --> WebAPI["/api/web/*"]
    Console --> ChatAPI["/api/chat* /api/sessions* /api/roles*"]
    Messenger --> ChatAPI
    Stage --> StageAPI["/api/stage/events SSE"]
    Characters --> CharacterAPI["/api/character-profiles*"]
    Models --> ModelAPI["/api/llm-models"]
    Voice --> VoiceAPI["/api/voice-models"]
    Live2D --> Live2DAPI["/api/live2d-models"]
    OpenWebUI --> BridgeAPI["/api/openwebui/*"]
    Deployment --> DeployAPI["/api/deployment/status"]
```

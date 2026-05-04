# EchoBot Web Mobile Integration Plan - 2026-04-29

## 中文版

### 目標

把 EchoBot 整合成 `moegundam/echobot-web-mobile` 私有管理版。第一階段目標是 Local Tunnel 內測：本機跑 EchoBot，Cloudflare Tunnel + Access 提供 HTTPS 與登入，iOS/Android 手機可用，10 人內測資料互相隔離。

### 專案範圍鎖定

| 項目 | 決策 |
|---|---|
| 唯一實作基底 | EchoBot |
| 修改方式 | 只在 `moegundam/echobot-web-mobile` 這個 EchoBot 私有 repo 內增量修改 |
| 不做事項 | 不建立雙專案架構、不合併 Open-LLM-VTuber backend、不搬整套外部服務 |
| 外部參考 | Open-LLM-VTuber 只作 Live2D / ASR / TTS / 語音 UX 的行為參考 |
| 後續節奏 | 先把 EchoBot 本機 web/mobile 能力穩住，再逐步補部署、真機、內測與模型 provider 設定流程 |

### 固定決策

| 項目 | 決策 |
|---|---|
| 主 repo | `KdaiP/EchoBot` |
| 私有 repo | `moegundam/echobot-web-mobile` |
| 參考 repo | `Open-LLM-VTuber/Open-LLM-VTuber`，只參考 Live2D / ASR / TTS / 語音 UX，不搬整套 backend，不作第二個實作基底 |
| 第一部署 profile | Local Tunnel |
| HTTPS/login | Cloudflare Tunnel + Cloudflare Access |
| EchoBot bind host | Local Tunnel 用 `127.0.0.1`，避免 LAN 繞過 Access |
| LLM | OpenAI-compatible API 預設，其他私有或本地 provider 只保留設定能力，不在公開文件寫入實際主機資訊 |
| Runtime data | `.echobot/users/<user_id>/...` |

### 規劃表

| Phase | 工作項 | 狀態 | 目前結果 | 驗證方式 | 阻塞 / 下一步 |
|---:|---|---|---|---|---|
| 0 | 檢查 skill / app / GitHub / Cloudflare 前置 | 已完成 | GitHub connector、Computer Use、Cloudflare skill、deployment skill 可用；`gh` CLI 已登入；`cloudflared` 已安裝 | `gh auth status`、`cloudflared --version` | Cloudflare origin cert/login 尚未完成，Tunnel/Access 放後面 |
| 1 | 建立私有 GitHub repo | 已完成 | 已建立 `moegundam/echobot-web-mobile`，來源為 `KdaiP/EchoBot` | GitHub repo 與 connector 可讀寫 | 無 |
| 2 | 建立工作分支與 PR | 已完成 | `feat/web-mobile-local-tunnel` 已推送；Draft PR #1 已建立 | GitHub PR #1，compare `main...feat/web-mobile-local-tunnel` | 後續補 commit 推到同一 PR |
| 3 | Local Tunnel 部署文件與 env 範本 | 已完成 | 新增 `.env.local-tunnel.example`、Cloudflare Tunnel 範例 config、雙語 local tunnel 文件 | 文件檢視、env key 檢查 | 等 Cloudflare 實際 domain/tunnel 資訊填入 |
| 4 | Cloudflare Access trusted-user header | 已完成 | `/web`、`/api/*`、ASR WebSocket 支援可信 header 模式，缺失/非法可拒絕 | pytest trusted-header tests | Cloudflare Access 實機驗證未做 |
| 5 | 多使用者資料隔離 | 已完成 | runtime data 依 user namespace 寫入 `.echobot/users/<user>/...`；ASR/TTS service instance 已改為 per-user | pytest user isolation tests、ASR provider isolation test | 需要 10 人內測壓測 |
| 6 | Mobile ASR/TTS 行為 | 已完成本機版 | SenseVoice ASR 與 Silero VAD 已下載並 ready；TTS 播放時暫停 ASR，播放後恢復；背景/鎖屏停止錄音；停止語音不取消 Agent job；停止語音會 abort pending TTS request；錄音啟動失敗會顯示權限/裝置/瀏覽器支援錯誤並重置 UI | JS syntax check、pytest route tests、`curl /api/web/asr/status` | 真機麥克風/TTS/Live2D 尚未驗證 |
| 7 | Mobile layout | 已完成第一版 | 360/390/430/768 viewport 的 stage、drawer、composer CSS 已調整並 smoke 通過；Live2D transform 已改為 stage-size aware，避免桌面保存位置裁切手機角色 | Chrome DevTools MCP viewport smoke | Playwright CLI 未安裝；本輪以 Chrome DevTools MCP 驗證 |
| 8 | Local app startup | 已完成 | 修正 `LLM_TIMEOUT` slots 預設 bug；本機 app 已可用 dummy env 啟動 | `python -m echobot app`、`curl /api/health`、`curl /web`、`curl /docs` | 推送仍在進行 |
| 9 | Cloudflare Tunnel 實際建立與 Access policy | 延後 | `cloudflared` 已安裝；尚未完成 Cloudflare browser login / origin cert，尚未建立 named tunnel / DNS route / Access app | `cloudflared tunnel ingress validate`、HTTPS `/web` | 依使用者指示先放後面；之後需要 Cloudflare 登入、hostname、Access email 名單 |
| 10 | Open-LLM-VTuber 參考差距盤點 | 已完成 | 新增 reference gap note，明確列出 Live2D / ASR / TTS / voice UX 差距與第一階段取捨 | `docs/implementation/open-llm-vtuber-reference-gap.md` | 第二階段再評估桌寵/VTube Studio 類體驗 |
| 11 | Full regression | 已完成 | 本輪全量 pytest 已通過：`308 passed`，含 Open WebUI bridge、Model Profiles、channel secret redaction、admin allowlist、gateway user-scope 與 local model roleplay fallback 測試 | `.venv/bin/python -m pytest` | 無 |
| 12 | Shell UI 語言切換 | 已完成 | `/stage`、`/messenger`、`/admin`、`/admin/guide`、`/admin/structure`、`/admin/channels`、`/admin/models`、`/admin/openwebui`、`/console` 新增共用 language switcher；預設英文，支援繁體中文與簡體中文，並以 `localStorage` 保存選擇 | `node --check`、trusted-route pytest、Chrome DevTools language smoke、mobile overflow smoke | 原大型 `/web`/`/console` 深層文案尚未全面 i18n，目前先補 console shell 與頂部操作文案 |
| 13 | Admin 操作說明頁 | 已完成 | `/admin` 新增「操作說明」入口；`/admin/guide` 以三語說明頁面用途、操作流程、設定檢查、預期成果、故障判斷與排除流程 | `node --check echobot/app/web/guide-app.js`、trusted-route pytest | 後續可在 Cloudflare/真機長跑後補更多實測案例 |
| 14 | Open WebUI 操作員 Bridge 介面 | 已完成本機介面 | 新增 `/admin/openwebui` 三語說明頁與 `/api/openwebui/*` narrow bridge；Open WebUI 可匯入專用 tool spec，但尚未實際接線 | `node --check`、`py_compile`、Open WebUI bridge pytest | 真正 Open WebUI 設定、bearer token 佈署與外部接線放後面 |
| 15 | 全頁解析度 / 裝置 / 直橫向顯示模式 | 已完成第一版 | 新增共用 `shell-display-mode.js`，所有頁面都有 Display Mode：預設 Auto 自動偵測 viewport、orientation、pointer type；使用者可手動切換 Portrait、Landscape、Desktop/Dense，選擇寫入 `localStorage`；HTML/JS/CSS asset 已加版本參數避免舊快取卡住 | `node --check`、trusted-route pytest、Chrome DevTools console/stage portrait/landscape smoke | 真機直橫向手感與每頁細部密度仍需後續調整 |
| 16 | Model Profiles 角色模型設定頁 | 已完成本機版 | 新增 `/admin/models` 三語模型設定頁，提供預設 A-E profile，並可持續新增自訂名稱 profile；每個 trusted user 獨立儲存模型/base URL 到 `.echobot/users/<user>/model_profiles.json`，API key 存到 `.echobot/users/<user>/model_profile_secrets.json` 且不回傳明文；啟用 profile 後會立即套用 chat LLM、TTS、ASR provider，並讓 `/console` 重新載入後換 Live2D/TTS 偏好 | `node --check`、`py_compile`、model profile targeted pytest | 後續可加 per-session/per-role 綁定、secret manager 加密與長跑驗證 |
| 17 | Channels 後台通訊平台頁 | 已完成第一版 | 新增 `/admin/channels` 三語只讀頁，集中呈現 runtime channel definitions/config/status，並把 LINE、Discord、WhatsApp 等規劃中 gateway 放到同一後台入口；Web page routes 改為 `WEB_PAGE_ROUTES` registry，避免新增頁面時散落手寫 route | `node --check`、route registry pytest、trusted-route pytest、browser smoke、full pytest | Token 輸入、webhook 驗證與平台 adapter 實作仍需後續切片 |
| 18 | PR 更新與收尾 | 未開始 | PR #1 存在且 mergeable | `git push`、GitHub PR check | 等本機第二輪驗證完成後補 commit |

### 必做驗收清單

| 類別 | 驗收項 | 狀態 |
|---|---|---|
| 本機服務 | `python -m echobot app --host 127.0.0.1 --port 8000` 可啟動 | 已完成 smoke |
| 本機服務 | `GET /api/health` 回 200 | 已完成 smoke |
| Web UI | `/web` 可載入 | 已完成 smoke |
| Auth | trusted header 缺失/非法拒絕 | 已完成測試 |
| Auth | Cloudflare Access email header 實際通過 | 未完成 |
| WebSocket | `/api/web/asr/ws` 在 trusted header 模式下可連線 | 已完成測試 |
| Voice | SenseVoice ASR / Silero VAD ready，錄音按鈕可用 | 已完成本機 smoke |
| Phone mic | 手機 HTTPS 麥克風授權、錄音上傳、ASR 轉文字 | 已完成 quick tunnel smoke |
| LLM | OpenAI-compatible provider 設定可由 env 或 Model Profiles 切換 | 已完成設定介面；實際私有 provider 資訊不放公開文件 |
| Shell UI | 英文 / 繁中 / 簡中語言切換 | 已完成，覆蓋 `/stage`、`/messenger`、`/admin`、`/admin/guide`、`/admin/structure`、`/admin/channels`、`/admin/models`、`/admin/openwebui`、`/console` |
| Admin Guide | 操作、設定、預期成果、故障與排除說明 | 已完成，`/admin/guide` 三語可切換 |
| Open WebUI Bridge | `/admin/openwebui` 說明頁、專用 OpenAPI tool spec、Stage/session/chat bridge API | 已完成本機介面；未實際接 Open WebUI |
| Channels | `/admin/channels` 顯示 runtime channel 狀態、目前可用 Telegram/QQ/Console 與規劃中 LINE/Discord/WhatsApp gateway | 已完成第一版只讀頁；後續再加入 token 輸入與 adapter |
| Adaptive Layout | 使用者可切換或自動偵測解析度 / 裝置 / 直橫向來調整所有頁面 | 已完成第一版；覆蓋 `/stage`、`/messenger`、`/admin`、`/admin/guide`、`/admin/structure`、`/admin/channels`、`/admin/models`、`/admin/openwebui`、`/console` |
| Model Profiles | `/admin/models` 可設定預設 A-E 與自訂新增模型 profile，啟用後 `/console` 會套用 chat/ASR/Live2D/TTS 選擇 | 已完成本機版；可填 API key 與 provider base URL，API key 只存 per-user secret 檔且 API 不回傳明文 |
| Mobile | 390x844 / 430x932 / 360x800 / 768x1024 無重疊 | 已完成 Chrome DevTools smoke |
| iPhone | Safari 登入、麥克風、ASR、TTS、Live2D lip sync | 未完成真機 |
| Android | Chrome 登入、麥克風、常開麥、ASR、TTS、Live2D lip sync | 未完成真機 |
| Regression | 全量 pytest | 已完成，`308 passed` |

### 需要使用者接手或確認的項目

| 項目 | 原因 | 何時需要 |
|---|---|---|
| 安裝 `cloudflared` | 安裝軟體需要 action-time 確認 | Phase 9 開始前 |
| Cloudflare domain / zone 選擇 | named tunnel 和 DNS route 需要知道 hostname | 建立 tunnel 前 |
| Cloudflare Access policy 成員名單 | 10 人內測登入名單需要你決定 | 建立 Access app 前 |
| Open WebUI bearer token 佈署 | 實際接 Open WebUI 前要產生強 token，並在 EchoBot env 與 Open WebUI tool server 設定同值 | Open WebUI 實際接線前 |
| 模型 provider secrets | `/admin/models` 已可保存 per-user API key，但目前是本機 secret JSON 檔；正式內測前可再升級為 OS keychain 或 secret manager | 正式多人內測前 |
| 直橫向真機體感確認 | 模擬 viewport 已檢查不重疊，但 Stage/Live2D/錄音操作的直橫向手感仍要真機確認 | Phase 17 第一版完成後的後續微調 |
| 真機測試 | iOS/Android 麥克風與瀏覽器權限必須用真機確認 | Phase 12 前 |

## English version

### Goal

Turn EchoBot into the private managed repo `moegundam/echobot-web-mobile`. The first target is Local Tunnel testing: EchoBot runs locally, Cloudflare Tunnel + Access provides HTTPS and login, iOS/Android phones work, and runtime data is isolated for a 10-person test group.

### Project Scope Lock

| Item | Decision |
|---|---|
| Single implementation base | EchoBot |
| Change strategy | Make incremental changes only inside the `moegundam/echobot-web-mobile` private EchoBot repo |
| Explicit non-goals | Do not create a dual-project architecture, do not merge the Open-LLM-VTuber backend, and do not import an entire external service stack |
| External reference | Open-LLM-VTuber is only a behavior reference for Live2D / ASR / TTS / voice UX |
| Forward pace | Stabilize EchoBot local web/mobile first, then add deployment, real-device checks, test group operation, and model-provider configuration in stages |

### Fixed Decisions

| Item | Decision |
|---|---|
| Main repo | `KdaiP/EchoBot` |
| Private repo | `moegundam/echobot-web-mobile` |
| Reference repo | `Open-LLM-VTuber/Open-LLM-VTuber`, reference only for Live2D / ASR / TTS / voice UX; not a second implementation base |
| First deployment profile | Local Tunnel |
| HTTPS/login | Cloudflare Tunnel + Cloudflare Access |
| EchoBot bind host | `127.0.0.1` for Local Tunnel to avoid LAN bypassing Access |
| LLM | OpenAI-compatible API by default; private or local providers are supported by configuration, but real host details do not belong in public docs |
| Runtime data | `.echobot/users/<user_id>/...` |

### Plan Table

| Phase | Work Item | Status | Current Result | Verification | Blocker / Next Step |
|---:|---|---|---|---|---|
| 0 | Check skills / apps / GitHub / Cloudflare prerequisites | Done | GitHub connector, Computer Use, Cloudflare skill, and deployment skill are available; `gh` is logged in; `cloudflared` is installed | `gh auth status`, `cloudflared --version` | Cloudflare origin cert/login is not complete; Tunnel/Access is deferred |
| 1 | Create private GitHub repo | Done | `moegundam/echobot-web-mobile` exists, imported from `KdaiP/EchoBot` | GitHub repo and connector access | None |
| 2 | Create work branch and PR | Done | `feat/web-mobile-local-tunnel` pushed; Draft PR #1 created | GitHub PR #1 and compare view | Push follow-up commits to the same PR |
| 3 | Local Tunnel docs and env template | Done | Added `.env.local-tunnel.example`, Cloudflare Tunnel example config, and bilingual local tunnel docs | Doc review and env key check | Fill real Cloudflare domain/tunnel values later |
| 4 | Cloudflare Access trusted-user header | Done | `/web`, `/api/*`, and ASR WebSocket support trusted-header mode with rejection for missing/invalid users | pytest trusted-header tests | Real Cloudflare Access validation pending |
| 5 | Multi-user data isolation | Done | Runtime data is scoped under `.echobot/users/<user>/...`; ASR/TTS service instances are now per-user | pytest user isolation tests, ASR provider isolation test | 10-person load test pending |
| 6 | Mobile ASR/TTS behavior | Local version done | SenseVoice ASR and Silero VAD are downloaded and ready; ASR pauses during TTS, resumes after playback, stops on background/pagehide, stop speech does not cancel Agent jobs, pending TTS requests are aborted on stop, and recording startup failures reset the UI with permission/device/browser support errors | JS syntax check, pytest route tests, `curl /api/web/asr/status` | Real phone microphone/TTS/Live2D validation pending |
| 7 | Mobile layout | First version done | CSS updated and smoke-tested for 360/390/430/768 stage, drawer, and composer behavior; Live2D transforms are now stage-size aware so desktop saved placement cannot crop the mobile character | Chrome DevTools MCP viewport smoke | Playwright CLI is missing; this round used Chrome DevTools MCP |
| 8 | Local app startup | Done | Fixed the `LLM_TIMEOUT` slots default bug; local app starts with dummy env | `python -m echobot app`, `curl /api/health`, `curl /web`, `curl /docs` | Push still pending |
| 9 | Create Cloudflare Tunnel and Access policy | Deferred | `cloudflared` is installed; Cloudflare browser login / origin cert is not complete; no named tunnel / DNS route / Access app yet | `cloudflared tunnel ingress validate`, HTTPS `/web` | Deferred by user request; later needs Cloudflare login, hostname, and Access email list |
| 10 | Open-LLM-VTuber reference gap list | Done | Added a reference gap note covering Live2D / ASR / TTS / voice UX gaps and phase-1 scope | `docs/implementation/open-llm-vtuber-reference-gap.md` | Re-evaluate desktop pet / VTube Studio-like mode in phase 2 |
| 11 | Full regression | Done | This round's full pytest passed: `308 passed`, including Open WebUI bridge, Model Profiles, channel secret redaction, admin allowlist, gateway user-scope, and local model roleplay fallback tests | `.venv/bin/python -m pytest` | None |
| 12 | Shell UI language switcher | Done | `/stage`, `/messenger`, `/admin`, `/admin/guide`, `/admin/structure`, `/admin/channels`, `/admin/models`, `/admin/openwebui`, and `/console` now share a language switcher; default English, Traditional Chinese, and Simplified Chinese are supported, with the choice saved in `localStorage` | `node --check`, trusted-route pytest, Chrome DevTools language smoke, mobile overflow smoke | Full deep i18n for the large existing `/web`/`/console` console is not done yet; this adds console shell and top action labels first |
| 13 | Admin operation guide page | Done | `/admin` now links to an Operation Guide; `/admin/guide` explains page roles, operation flow, configuration checklist, expected healthy results, failure signs, and troubleshooting in three languages | `node --check echobot/app/web/guide-app.js`, trusted-route pytest | Add more real Cloudflare and device long-run cases later |
| 14 | Open WebUI operator bridge interface | Local interface done | Added `/admin/openwebui` in three languages and a narrow `/api/openwebui/*` bridge; Open WebUI can import the dedicated tool spec, but it has not been wired to a real Open WebUI instance yet | `node --check`, `py_compile`, Open WebUI bridge pytest | Real Open WebUI configuration, bearer-token deployment, and external wiring are deferred |
| 15 | All-page resolution / device / orientation display modes | First version done | Added shared `shell-display-mode.js`; every page has Display Mode: Auto detects viewport, orientation, and pointer type; users can manually switch Portrait, Landscape, Desktop/Dense, with the choice saved in `localStorage`; HTML/JS/CSS assets now carry a version query to avoid stale browser cache | `node --check`, trusted-route pytest, Chrome DevTools console/stage portrait/landscape smoke | Real-device portrait/landscape feel and finer per-page density tuning still need follow-up |
| 16 | Model Profiles role model settings page | Local version done | Added `/admin/models` in three languages with default A-E profiles plus user-created named profiles; each trusted user stores model/base URL settings in `.echobot/users/<user>/model_profiles.json`, stores API keys in `.echobot/users/<user>/model_profile_secrets.json`, and never receives plaintext keys in API responses; activating a profile applies chat LLM, TTS, and ASR providers immediately and lets `/console` reload into the selected Live2D/TTS preferences | `node --check`, `py_compile`, model profile targeted pytest | Per-session/per-role binding, secret-manager encryption, and long-run validation can be added later |
| 17 | Channels admin messaging page | First version done | Added `/admin/channels` as a trilingual read-only page for runtime channel definitions/config/status, and placed planned LINE, Discord, and WhatsApp gateways under the same back-office entry; Web page routes now use a `WEB_PAGE_ROUTES` registry so new pages do not require scattered handwritten routes | `node --check`, route registry pytest, trusted-route pytest, browser smoke, full pytest | Token entry, webhook verification, and platform adapter implementation remain future slices |
| 18 | PR update and closeout | Not started | PR #1 exists and is mergeable | `git push`, GitHub PR check | Push a follow-up commit after the second local verification round |

### Required Acceptance Checklist

| Category | Acceptance Item | Status |
|---|---|---|
| Local service | `python -m echobot app --host 127.0.0.1 --port 8000` starts | Smoke done |
| Local service | `GET /api/health` returns 200 | Smoke done |
| Web UI | `/web` loads | Smoke done |
| Auth | Missing/invalid trusted header is rejected | Tested |
| Auth | Real Cloudflare Access email header passes | Not done |
| WebSocket | `/api/web/asr/ws` works in trusted-header mode | Tested |
| Voice | SenseVoice ASR / Silero VAD are ready and the record button is enabled | Local smoke done |
| Phone mic | Phone HTTPS microphone permission, audio upload, and ASR transcription | Quick tunnel smoke done |
| LLM | OpenAI-compatible provider settings can be switched by env or Model Profiles | Settings interface done; real private provider details are intentionally excluded from public docs |
| Shell UI | English / Traditional Chinese / Simplified Chinese language switching | Done for `/stage`, `/messenger`, `/admin`, `/admin/guide`, `/admin/structure`, `/admin/channels`, `/admin/models`, `/admin/openwebui`, and `/console` |
| Admin Guide | Operation, configuration, expected-result, failure, and troubleshooting guide | Done; `/admin/guide` supports all three languages |
| Open WebUI Bridge | `/admin/openwebui` guide page, dedicated OpenAPI tool spec, and Stage/session/chat bridge APIs | Local interface done; not wired to a real Open WebUI instance |
| Channels | `/admin/channels` shows runtime channel status, available Telegram/QQ/Console channels, and planned LINE/Discord/WhatsApp gateways | First read-only version done; token entry and adapters remain follow-up work |
| Adaptive Layout | Users can switch or auto-detect resolution / device / orientation to adjust every page | First version done for `/stage`, `/messenger`, `/admin`, `/admin/guide`, `/admin/structure`, `/admin/channels`, `/admin/models`, `/admin/openwebui`, and `/console` |
| Model Profiles | `/admin/models` can configure default A-E and user-created model profiles, and activating one applies chat/ASR/Live2D/TTS choices to `/console` | Local version done; users can enter API keys and provider base URLs; API keys are stored only in per-user secret files and are never returned in plaintext |
| Mobile | 390x844 / 430x932 / 360x800 / 768x1024 have no overlap | Chrome DevTools smoke done |
| iPhone | Safari login, mic, ASR, TTS, Live2D lip sync | Real-device pending |
| Android | Chrome login, mic, open mic, ASR, TTS, Live2D lip sync | Real-device pending |
| Regression | Full pytest | Done, `308 passed` |

### User Handoff Or Confirmation Needed

| Item | Reason | Needed When |
|---|---|---|
| Install `cloudflared` | Software installation needs action-time confirmation | Before Phase 9 |
| Cloudflare domain / zone choice | Named tunnel and DNS route need a hostname | Before creating the tunnel |
| Cloudflare Access policy member list | The 10-person test login list must be chosen by you | Before creating the Access app |
| Open WebUI bearer token deployment | Before real Open WebUI wiring, generate one strong token and set the same value in EchoBot env and Open WebUI tool server auth | Before real Open WebUI wiring |
| Model provider secrets | `/admin/models` can now store per-user API keys, but the current storage is a local secret JSON file; upgrade to OS keychain or a secret manager before broader private testing if needed | Before broader multi-user testing |
| Real-device orientation feel check | Simulated viewports now catch overlap, but Stage/Live2D/recording ergonomics in portrait/landscape still need real-device confirmation | Follow-up tuning after the Phase 17 first version |
| Real-device testing | iOS/Android microphone and browser permissions must be verified on real devices | Before Phase 12 closeout |

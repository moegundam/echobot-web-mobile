# EchoBot Web Mobile Integration Plan - 2026-04-29

## 中文版

### 目標

把 EchoBot 整合成 `moegundam/echobot-web-mobile` Web/Mobile 管理版。第一階段目標是 Local Tunnel 內測：本機跑 EchoBot，Cloudflare Tunnel + Access 提供 HTTPS 與登入，iOS/Android 手機可用，10 人內測資料互相隔離。

### 專案範圍鎖定

| 項目 | 決策 |
|---|---|
| 唯一實作基底 | EchoBot |
| 修改方式 | 只在 `moegundam/echobot-web-mobile` 這個 EchoBot 管理 repo 內增量修改 |
| 不做事項 | 不建立雙專案架構、不合併 Open-LLM-VTuber backend、不搬整套外部服務 |
| 外部參考 | Open-LLM-VTuber 只作 Live2D / ASR / TTS / 語音 UX 的行為參考 |
| 後續節奏 | 先把 EchoBot 本機 web/mobile 能力穩住，再逐步補部署、真機、內測與模型 provider 設定流程 |

### 固定決策

| 項目 | 決策 |
|---|---|
| 主 repo | `KdaiP/EchoBot` |
| 管理 repo | `moegundam/echobot-web-mobile` |
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
| 2 | 建立工作分支與 PR | 已完成 | `feat/web-mobile-local-tunnel` 已完成並回到 `main`；`main` 已推送到 `origin/main` | GitHub PR #1、`main` branch、commits `7dbd910` / `22b7a34` | 無 |
| 3 | Local Tunnel 部署文件與 env 範本 | 已完成 | 新增 `.env.local-tunnel.example`、Cloudflare Tunnel 範例 config、雙語 local tunnel 文件 | 文件檢視、env key 檢查 | 等 Cloudflare 實際 domain/tunnel 資訊填入 |
| 4 | Cloudflare Access trusted-user header | 已完成 | `/web`、`/api/*`、ASR WebSocket 支援可信 header 模式，缺失/非法可拒絕 | pytest trusted-header tests | Cloudflare Access 實機驗證未做 |
| 5 | 多使用者資料隔離 | 已完成 | runtime data 依 user namespace 寫入 `.echobot/users/<user>/...`；ASR/TTS service instance 已改為 per-user | pytest user isolation tests、ASR provider isolation test | 需要 10 人內測壓測 |
| 6 | Mobile ASR/TTS 行為 | 已完成本機版 | SenseVoice ASR 與 Silero VAD 已下載並 ready；TTS 播放時暫停 ASR，播放後恢復；背景/鎖屏停止錄音；停止語音不取消 Agent job；停止語音會 abort pending TTS request；錄音啟動失敗會顯示權限/裝置/瀏覽器支援錯誤並重置 UI | JS syntax check、pytest route tests、`curl /api/web/asr/status` | 真機麥克風/TTS/Live2D 尚未驗證 |
| 7 | Mobile layout | 已完成第一版 | 360/390/430/768 viewport 的 stage、drawer、composer CSS 已調整並 smoke 通過；Live2D transform 已改為 stage-size aware，避免桌面保存位置裁切手機角色；Playwright/Chromium 本機 browser smoke 已安裝並通過 | Chrome DevTools MCP viewport smoke、`.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001` | HTTPS 真機驗證依使用者指示延後 |
| 8 | Local app startup | 已完成 | 修正 `LLM_TIMEOUT` slots 預設 bug；本機 app 已可用 dummy env 啟動；後續 CI commit 已推送到 `main` | `python -m echobot app`、`curl /api/health`、`curl /web`、`curl /docs`、GitHub Actions | 無 |
| 9 | Cloudflare Tunnel 實際建立與 Access policy | 部分完成 | `cloudflared` 已安裝但尚未完成 Cloudflare browser login / origin cert，尚未建立 named tunnel / DNS route / Access app；本機 app 與 remote Open WebUI reverse tunnel 已改由 macOS launchd 管理，並新增 `scripts/echobot_entrypoint.py` doctor/status/smoke | `scripts/echobot_entrypoint.py doctor/status/smoke-openwebui`、launchd status、HTTPS `/web` 待 Cloudflare | Cloudflare 正式 HTTPS 仍需要登入、hostname、Access email 名單；真機 HTTPS 驗收依使用者指示跳過 |
| 10 | Open-LLM-VTuber 參考差距盤點 | 已完成 | 新增 reference gap note，明確列出 Live2D / ASR / TTS / voice UX 差距與第一階段取捨 | `docs/implementation/open-llm-vtuber-reference-gap.md` | 第二階段再評估桌寵/VTube Studio 類體驗 |
| 11 | Full regression | 已完成 | 本輪全量 pytest 已通過：`363 passed, 2 warnings`，含 Open WebUI bridge、LLM/Voice/Live2D profile split、Character Profiles、Character Packages、Stage emotion/motion event、channel secret redaction、admin allowlist、channel smoke、gateway user-scope、Telegram/Discord true E2E support、Discord native adapter 與 local model roleplay fallback 測試 | `.venv/bin/python -m pytest -q` | 無 |
| 12 | Shell UI 語言切換 | 已完成 | `/stage`、`/messenger`、`/admin`、`/admin/guide`、`/admin/structure`、`/admin/characters`、`/admin/channels`、`/admin/models`、`/admin/openwebui`、`/console` 新增共用 language switcher；預設英文，支援繁體中文與簡體中文，並以 `localStorage` 保存選擇 | `node --check`、trusted-route pytest、Chrome DevTools language smoke、mobile overflow smoke | 原大型 `/web`/`/console` 深層文案尚未全面 i18n，目前先補 console shell 與頂部操作文案 |
| 13 | Admin 操作說明頁 | 已完成 | `/admin` 新增「操作說明」入口；`/admin/guide` 以三語說明頁面用途、操作流程、設定檢查、預期成果、故障判斷與排除流程 | `node --check echobot/app/web/guide-app.js`、trusted-route pytest | 後續可在 Cloudflare/真機長跑後補更多實測案例 |
| 14 | Open WebUI 操作員 Bridge 介面 | 已完成接口、本機 smoke、remote Open WebUI reachability smoke 與 launchd 穩定入口 | 新增 `/admin/openwebui` 三語說明頁與 `/api/openwebui/*` narrow bridge；Open WebUI 可匯入專用 tool spec；狀態頁會顯示 token、target user、allowlist、operator-agent mode 風險；`scripts/openwebui_bridge_smoke.py` 可用 bearer token 或 runtime-only token file 驗證 tool spec、sessions、stage event 與 chat call；`scripts/echobot_entrypoint.py` 可管理本機 app 與 remote Open WebUI reverse tunnel launchd，並從 remote Open WebUI host 視角重跑 smoke | `node --check`、`py_compile`、Open WebUI bridge pytest、Open WebUI bridge smoke script、remote Open WebUI reverse tunnel smoke、launchd status | Open WebUI 後台 tool server 註冊仍需要該服務 UI 或持久化設定；Cloudflare Tunnel/Access 仍是正式 HTTPS 入口 |
| 15 | 全頁解析度 / 裝置 / 直橫向顯示模式 | 已完成第一版 | 新增共用 `shell-display-mode.js`，所有頁面都有 Display Mode：預設 Auto 自動偵測 viewport、orientation、pointer type；使用者可手動切換 Portrait、Landscape、Desktop/Dense，選擇寫入 `localStorage`；HTML/JS/CSS asset 已加版本參數避免舊快取卡住 | `node --check`、trusted-route pytest、Chrome DevTools console/stage portrait/landscape smoke | 真機直橫向手感與每頁細部密度仍需後續調整 |
| 16 | Runtime Profiles 分頁 | 已完成本機版 | `/admin/models` 只管理 LLM provider/model/base URL/API key/推理參數；`/admin/voice-models` 管理 STT/TTS；`/admin/live2d` 管理 Live2D selection 與視覺 profile；每個 trusted user 獨立儲存設定，API key 存到 per-user secret 檔且不回傳明文；`/admin/characters` 負責把 LLM、Voice、Live2D 綁成角色互動單位，`/console` 可做臨時 runtime override 並套用到 Stage | `node --check`、`py_compile`、runtime profile targeted pytest | 後續可加 secret manager 加密與長跑驗證 |
| 17 | Channels 後台通訊平台頁 | 已完成第四版 | `/admin/channels` 已支援 Telegram / Discord 設定表單、secret redaction、admin-gated save、`POST /api/channels/{channel}/smoke` readiness check；正式通訊 gateway 可用 `mirror_to_stage` / `stage_session_name` 把回覆同步到 `/stage`；新增 secret-free `GET /api/channels/stage-targets`，讓 `/stage` 與 `/messenger` 可直接選擇 Telegram/Discord 等已設定 target，不必手動輸入 session；Telegram 已用 repo 外 token 驗證 Bot API `getMe`、poller 啟動、Bot API outbound、session 綁定、真實 Telegram Desktop `/ping TG_OK` inbound 回覆與 Stage mirror；Discord 已用真 bot `/ping DISCORD_OK` 驗證 gateway 回覆與 Stage mirror；通訊 gateway 內建 deterministic `/ping` / `/smoke` 指令 | `node --check`、channel targeted pytest、web static pytest、Telegram true E2E、Discord true E2E、Stage mirror SSE、Discord native adapter unit tests、敏感字串掃描 | LINE/WhatsApp adapter 與公開 webhook/真實平台長跑測試仍需後續切片；QQ 真實平台長跑測試尚未完成 |
| 23 | CI / 公開安全 / Browser smoke 工具 | 已完成 | 新增 GitHub Actions CI，執行 dependency install、JS syntax、Python compile、public safety scan、whitespace check 與 pytest；CI 已推送到 `main` 且 GitHub Actions 通過；新增 `scripts/check_public_safety.py` 阻擋 tracked `.echobot/`、非 example env 與常見真 secret；新增 `scripts/browser_smoke.py`，Playwright/Chromium 已安裝且本機多 viewport smoke 通過 | GitHub Actions passed、`python scripts/check_public_safety.py`、`.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001` | 無 |
| 18 | Character Profiles 角色設定頁 | 已完成第一版 | 新增 `/admin/characters` 三語角色設定頁與 `/api/character-profiles*` 聚合 API；角色 prompt、LLM/Voice/Live2D 綁定、有效 chat/TTS/ASR/Live2D 摘要可在同一頁管理；資料仍沿用 role card 與 split profile binding，不新增第二套角色儲存格式 | targeted pytest、web static pytest、`node --check`、`py_compile` | 後續補角色 package 進階批量管理 |
| 19 | Stage emotion / motion event | 已完成第一版 | `StageEvent` 與 Open WebUI bridge 可攜帶 `emotion`、`expression`、`motion`；新增 `character_state` event；`/stage` 會依 Live2D config 套用 expression/motion；`/messenger` final 回覆支援 `[emotion:...] [expression:...] [motion:...]` 標籤並只以 `textContent` 顯示文字 | `363 passed, 2 warnings`、JS syntax、`py_compile`、`git diff --check`、敏感字串掃描 | 下一步可做角色 package 進階批量管理 |
| 20 | Character emotion map | 已完成本機版 | `/admin/characters` 可為每個角色新增、命名與維護 emotion-to-expression/motion map；`/api/stage/events` 與 Open WebUI bridge 在事件缺少 explicit expression/motion 時，會依目前 session 綁定角色自動套用 map；新增 `scripts/live2d_asset_smoke.py` 驗證 bundled Live2D model3、texture、expression、motion 與 Stage event directive | `363 passed, 2 warnings`、JS syntax、`py_compile`、`git diff --check`、敏感字串掃描、Live2D asset smoke | HTTPS 真機前台效果仍需後續驗收 |
| 21 | Character package 匯入/匯出 | 已完成本機版 | `/admin/characters` 可匯出單一角色 JSON package，內容包含 prompt、LLM/Voice/Live2D 綁定、emotion map 與非敏感模型設定快照；匯入可改名或覆蓋既有角色，匯出不包含明文 API key/secrets | `363 passed, 2 warnings`、JS syntax、`py_compile`、`git diff --check`、敏感字串掃描 | v1 不打包 Live2D asset，不做批量角色庫 |
| 22 | PR 更新與收尾 | 已完成 | 收尾 commit 已推送到 `main`；GitHub Actions 已通過；PR closeout 不再有待推送事項 | `git push`、GitHub PR check、GitHub Actions passed | 無 |
| 24 | Console/Admin UX consistency | 已完成本輪可自動修復項 | 修正 page title 走 i18n、Sessions route mode 不再顯示 raw enum、Session card 顯示語系化 route label、Messenger 改讀 session route mode、Stage/Messenger 補跨頁導覽、Console shell safety 顯示語系化標籤、Runtime 覆寫加上全域範圍提示、Open WebUI 頁補 launchd/entrypoint 指令、Channels 頁補平台實測狀態 | `node --check`、`tests/test_web_static.py`、browser smoke、full pytest | 真機 HTTPS 驗收依使用者指示跳過；LINE/WhatsApp runtime adapter 尚未接線；QQ 真實平台長跑未做 |

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
| LLM | OpenAI-compatible provider 設定可由 env 或 `/admin/models` LLM profile 切換 | 已完成設定介面；實際私有 provider 資訊不放公開文件 |
| Shell UI | 英文 / 繁中 / 簡中語言切換 | 已完成，覆蓋 `/stage`、`/messenger`、`/admin`、`/admin/guide`、`/admin/structure`、`/admin/channels`、`/admin/models`、`/admin/openwebui`、`/console` |
| Admin Guide | 操作、設定、預期成果、故障與排除說明 | 已完成，`/admin/guide` 三語可切換 |
| Open WebUI Bridge | `/admin/openwebui` 說明頁、專用 OpenAPI tool spec、Stage/session/chat bridge API 與本機 bridge smoke script | 已完成接口、本機 smoke、remote Open WebUI reverse smoke 與 launchd 穩定入口；遠端 Open WebUI UI 內啟用 tool server 仍需要該服務的登入/session |
| Stage Emotion | Stage event 與 Open WebUI bridge 可推送 emotion/expression/motion，`/stage` 可播放對應 Live2D 表情/動作；角色頁可維護 emotion map 並由後端自動補上 expression/motion | 已完成本機版；真機 Live2D 模型動作效果仍需視模型 assets 驗證 |
| Character Packages | `/admin/characters` 可匯出/匯入單一角色 JSON package，且不包含 secrets | 已完成本機版；v1 不打包 Live2D asset |
| Console/Admin UX | route mode、shell safety、session links、Stage/Messenger 跨頁導覽與 Open WebUI/Channels 狀態說明 | 已完成本輪可自動修復項；真機 HTTPS 與未具備憑證的平台不納入本輪 |
| Channels | `/admin/channels` 顯示 runtime channel 狀態、Telegram / Discord 設定與 smoke readiness，並保留 LINE/WhatsApp 後續 gateway 入口 | 已完成第三版；Telegram token/poller/outbound readiness、session 綁定與 Stage target projection 已通過；Discord webhook bridge、outbound webhook 與 native bot adapter 已有測試；LINE/WhatsApp runtime adapter 與公開 webhook/真實平台長跑測試仍需後續切片 |
| Adaptive Layout | 使用者可切換或自動偵測解析度 / 裝置 / 直橫向來調整所有頁面 | 已完成第一版；覆蓋 `/stage`、`/messenger`、`/admin`、`/admin/guide`、`/admin/structure`、`/admin/channels`、`/admin/models`、`/admin/openwebui`、`/console` |
| Runtime Profiles | `/admin/models`、`/admin/voice-models`、`/admin/live2d` 分別管理 LLM、STT/TTS 與 Live2D；`/admin/characters` 綁定角色，`/console` 做目前 session 的臨時測試覆寫 | 已完成本機版；API key 只存 per-user secret 檔且 API 不回傳明文 |
| Mobile | 390x844 / 430x932 / 360x800 / 768x1024 無重疊 | 已完成 Chrome DevTools smoke |
| iPhone | Safari 登入、麥克風、ASR、TTS、Live2D lip sync | 未完成真機 |
| Android | Chrome 登入、麥克風、常開麥、ASR、TTS、Live2D lip sync | 未完成真機 |
| Regression | 全量 pytest | 已完成，最新為 `363 passed, 2 warnings` |

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

Turn EchoBot into the Web/Mobile management repo `moegundam/echobot-web-mobile`. The first target is Local Tunnel testing: EchoBot runs locally, Cloudflare Tunnel + Access provides HTTPS and login, iOS/Android phones work, and runtime data is isolated for a 10-person test group.

### Project Scope Lock

| Item | Decision |
|---|---|
| Single implementation base | EchoBot |
| Change strategy | Make incremental changes only inside the `moegundam/echobot-web-mobile` EchoBot management repo |
| Explicit non-goals | Do not create a dual-project architecture, do not merge the Open-LLM-VTuber backend, and do not import an entire external service stack |
| External reference | Open-LLM-VTuber is only a behavior reference for Live2D / ASR / TTS / voice UX |
| Forward pace | Stabilize EchoBot local web/mobile first, then add deployment, real-device checks, test group operation, and model-provider configuration in stages |

### Fixed Decisions

| Item | Decision |
|---|---|
| Main repo | `KdaiP/EchoBot` |
| Management repo | `moegundam/echobot-web-mobile` |
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
| 2 | Create work branch and PR | Done | `feat/web-mobile-local-tunnel` is complete and the work is back on `main`; `main` has been pushed to `origin/main` | GitHub PR #1, `main` branch, commits `7dbd910` / `22b7a34` | None |
| 3 | Local Tunnel docs and env template | Done | Added `.env.local-tunnel.example`, Cloudflare Tunnel example config, and bilingual local tunnel docs | Doc review and env key check | Fill real Cloudflare domain/tunnel values later |
| 4 | Cloudflare Access trusted-user header | Done | `/web`, `/api/*`, and ASR WebSocket support trusted-header mode with rejection for missing/invalid users | pytest trusted-header tests | Real Cloudflare Access validation pending |
| 5 | Multi-user data isolation | Done | Runtime data is scoped under `.echobot/users/<user>/...`; ASR/TTS service instances are now per-user | pytest user isolation tests, ASR provider isolation test | 10-person load test pending |
| 6 | Mobile ASR/TTS behavior | Local version done | SenseVoice ASR and Silero VAD are downloaded and ready; ASR pauses during TTS, resumes after playback, stops on background/pagehide, stop speech does not cancel Agent jobs, pending TTS requests are aborted on stop, and recording startup failures reset the UI with permission/device/browser support errors | JS syntax check, pytest route tests, `curl /api/web/asr/status` | Real phone microphone/TTS/Live2D validation pending |
| 7 | Mobile layout | First version done | CSS updated and smoke-tested for 360/390/430/768 stage, drawer, and composer behavior; Live2D transforms are now stage-size aware so desktop saved placement cannot crop the mobile character; Playwright/Chromium local browser smoke is installed and passed | Chrome DevTools MCP viewport smoke; `.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001` | HTTPS real-device validation is deferred by request |
| 8 | Local app startup | Done | Fixed the `LLM_TIMEOUT` slots default bug; local app starts with dummy env; follow-up CI commit has been pushed to `main` | `python -m echobot app`, `curl /api/health`, `curl /web`, `curl /docs`, GitHub Actions | None |
| 9 | Create Cloudflare Tunnel and Access policy | Partially done | `cloudflared` is installed but Cloudflare browser login / origin cert is not complete; no named tunnel / DNS route / Access app yet. The local app and remote Open WebUI reverse tunnel now run under macOS launchd, with `scripts/echobot_entrypoint.py` doctor/status/smoke support | `scripts/echobot_entrypoint.py doctor/status/smoke-openwebui`, launchd status; HTTPS `/web` pending Cloudflare | Formal Cloudflare HTTPS still needs login, hostname, and Access email list; real-device HTTPS validation is skipped per user instruction |
| 10 | Open-LLM-VTuber reference gap list | Done | Added a reference gap note covering Live2D / ASR / TTS / voice UX gaps and phase-1 scope | `docs/implementation/open-llm-vtuber-reference-gap.md` | Re-evaluate desktop pet / VTube Studio-like mode in phase 2 |
| 11 | Full regression | Done | This round's full pytest passed: `363 passed, 2 warnings`, including Open WebUI bridge, the LLM/Voice/Live2D profile split, Character Profiles, Character Packages, Stage emotion/motion event, channel secret redaction, admin allowlist, channel smoke, gateway user-scope, Telegram/Discord true E2E support, Discord native adapter, and local model roleplay fallback tests | `.venv/bin/python -m pytest -q` | None |
| 12 | Shell UI language switcher | Done | `/stage`, `/messenger`, `/admin`, `/admin/guide`, `/admin/structure`, `/admin/characters`, `/admin/channels`, `/admin/models`, `/admin/openwebui`, and `/console` now share a language switcher; default English, Traditional Chinese, and Simplified Chinese are supported, with the choice saved in `localStorage` | `node --check`, trusted-route pytest, Chrome DevTools language smoke, mobile overflow smoke | Full deep i18n for the large existing `/web`/`/console` console is not done yet; this adds console shell and top action labels first |
| 13 | Admin operation guide page | Done | `/admin` now links to an Operation Guide; `/admin/guide` explains page roles, operation flow, configuration checklist, expected healthy results, failure signs, and troubleshooting in three languages | `node --check echobot/app/web/guide-app.js`, trusted-route pytest | Add more real Cloudflare and device long-run cases later |
| 14 | Open WebUI operator bridge interface | Bridge API, local smoke tooling, remote Open WebUI reachability smoke, and launchd stable entry done | Added `/admin/openwebui` in three languages and a narrow `/api/openwebui/*` bridge; Open WebUI can import the dedicated tool spec; the status page now shows token, target-user, allowlist, and operator-agent mode risk; `scripts/openwebui_bridge_smoke.py` validates the tool spec, sessions, stage events, and chat calls with a bearer token or runtime-only token file; `scripts/echobot_entrypoint.py` manages the local app and remote Open WebUI reverse tunnel under launchd and reruns smoke from the remote Open WebUI host point of view | `node --check`, `py_compile`, Open WebUI bridge pytest, Open WebUI bridge smoke script, remote Open WebUI reverse tunnel smoke, launchd status | Open WebUI tool-server registration still needs that service's UI or persistent config; Cloudflare Tunnel/Access remains the formal HTTPS entrypoint |
| 15 | All-page resolution / device / orientation display modes | First version done | Added shared `shell-display-mode.js`; every page has Display Mode: Auto detects viewport, orientation, and pointer type; users can manually switch Portrait, Landscape, Desktop/Dense, with the choice saved in `localStorage`; HTML/JS/CSS assets now carry a version query to avoid stale browser cache | `node --check`, trusted-route pytest, Chrome DevTools console/stage portrait/landscape smoke | Real-device portrait/landscape feel and finer per-page density tuning still need follow-up |
| 16 | Runtime Profiles split pages | Local version done | `/admin/models` manages only LLM provider/model/base URL/API key/inference parameters; `/admin/voice-models` manages STT/TTS; `/admin/live2d` manages Live2D selection and visual profiles; settings are user-scoped, API keys are stored in per-user secret files and are never returned in plaintext; `/admin/characters` binds LLM, Voice, and Live2D into one interaction unit, while `/console` can apply temporary runtime overrides to Stage | `node --check`, `py_compile`, runtime profile targeted pytest | Secret-manager encryption and long-run validation can be added later |
| 17 | Channels admin messaging page | Fourth version done | `/admin/channels` now supports Telegram / Discord settings forms, secret redaction, admin-gated save, and `POST /api/channels/{channel}/smoke` readiness checks; production messaging gateways can use `mirror_to_stage` / `stage_session_name` to show replies on `/stage`; added secret-free `GET /api/channels/stage-targets` so `/stage` and `/messenger` can select configured Telegram/Discord targets instead of typing a session; Telegram has passed Bot API `getMe`, poller startup, Bot API outbound, session binding, real Telegram Desktop `/ping TG_OK` inbound reply, and Stage mirror; Discord has passed real bot `/ping DISCORD_OK` gateway reply and Stage mirror; gateways now include deterministic `/ping` / `/smoke` commands | `node --check`, channel targeted pytest, web static pytest, Telegram true E2E, Discord true E2E, Stage mirror SSE, Discord native adapter unit tests, sensitive-string scan | LINE/WhatsApp adapters and public webhook / long-running real-platform tests remain future slices; QQ real-platform long-run testing is not done |
| 23 | CI / public safety / browser smoke tooling | Done | Added GitHub Actions CI for dependency install, JS syntax, Python compile, public safety scan, whitespace check, and pytest; CI has been pushed to `main` and GitHub Actions passed; added `scripts/check_public_safety.py` to block tracked `.echobot/`, non-example env files, and common real-secret patterns; added `scripts/browser_smoke.py`, with Playwright/Chromium installed and local multi-viewport smoke passing | GitHub Actions passed, `.venv/bin/python scripts/check_public_safety.py`, `.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001` | None |
| 18 | Character Profiles setup page | First version done | Added `/admin/characters` in three languages and the composed `/api/character-profiles*` API; role prompts, LLM/Voice/Live2D bindings, and effective chat/TTS/ASR/Live2D summaries are managed in one page; data still reuses role cards and split profile bindings instead of creating a second character store | targeted pytest, web static pytest, `node --check`, `py_compile` | Add advanced bulk character package management later |
| 19 | Stage emotion / motion event | First version done | `StageEvent` and the Open WebUI bridge can carry `emotion`, `expression`, and `motion`; added `character_state` events; `/stage` applies expression/motion from Live2D config; `/messenger` final replies support `[emotion:...] [expression:...] [motion:...]` tags and still render text only through `textContent` | `363 passed, 2 warnings`, JS syntax, `py_compile`, `git diff --check`, sensitive-string scan | Next step can be advanced bulk character package management |
| 20 | Character emotion map | Local version done | `/admin/characters` can create, name, and maintain emotion-to-expression/motion maps per character; `/api/stage/events` and the Open WebUI bridge apply the current session role's map when events omit explicit expression/motion values; `scripts/live2d_asset_smoke.py` validates bundled Live2D model3, texture, expression, motion, and Stage event directives | `363 passed, 2 warnings`, JS syntax, `py_compile`, `git diff --check`, sensitive-string scan, Live2D asset smoke | HTTPS real-device Stage effects still need follow-up validation |
| 21 | Character package import/export | Local version done | `/admin/characters` can export a single-character JSON package containing the prompt, LLM/Voice/Live2D bindings, emotion map, and non-sensitive model settings snapshot; import can rename or overwrite an existing character, and exports never include plaintext API keys/secrets | `363 passed, 2 warnings`, JS syntax, `py_compile`, `git diff --check`, sensitive-string scan | v1 does not bundle Live2D assets or provide a bulk character library |
| 22 | PR update and closeout | Done | Closeout commit has been pushed to `main`; GitHub Actions passed; PR closeout has no remaining push item | `git push`, GitHub PR check, GitHub Actions passed | None |
| 24 | Console/Admin UX consistency | This round's automatable fixes are done | Page titles now use i18n, Sessions route mode no longer shows raw enum values, Session cards render localized route labels, Messenger uses the selected Session route mode, Stage/Messenger have cross-surface navigation, Console shell safety labels are localized, runtime overrides show their global scope, the Open WebUI page includes launchd/entrypoint commands, and Channels shows verified-platform status | `node --check`, `tests/test_web_static.py`, browser smoke, full pytest | Real-device HTTPS is skipped per user instruction; LINE/WhatsApp runtime adapters are not wired; QQ real-platform long-run validation is not done |

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
| LLM | OpenAI-compatible provider settings can be switched by env or `/admin/models` LLM profiles | Settings interface done; real private provider details are intentionally excluded from public docs |
| Shell UI | English / Traditional Chinese / Simplified Chinese language switching | Done for `/stage`, `/messenger`, `/admin`, `/admin/guide`, `/admin/structure`, `/admin/channels`, `/admin/models`, `/admin/openwebui`, and `/console` |
| Admin Guide | Operation, configuration, expected-result, failure, and troubleshooting guide | Done; `/admin/guide` supports all three languages |
| Open WebUI Bridge | `/admin/openwebui` guide page, dedicated OpenAPI tool spec, Stage/session/chat bridge APIs, and local bridge smoke script | Bridge API and local smoke tooling done; remote Open WebUI UI enablement still needs that service's login/session |
| Stage Emotion | Stage events and Open WebUI bridge can push emotion/expression/motion, `/stage` can play matching Live2D expressions/motions, and character-level emotion maps can auto-fill expression/motion | Local version done; real-device/model-asset motion effect still needs validation |
| Character Packages | `/admin/characters` can export/import one character JSON package without secrets | Local version done; v1 does not bundle Live2D assets |
| Console/Admin UX | route mode, shell safety, session links, Stage/Messenger cross-navigation, and Open WebUI/Channels status wording | This round's automatable fixes are done; real-device HTTPS and platforms without available credentials are not included |
| Channels | `/admin/channels` shows runtime channel status, Telegram / Discord settings and smoke readiness, while retaining LINE/WhatsApp as follow-up gateway entries | Fourth version done; Telegram true E2E (`/ping TG_OK`) and Discord true E2E (`/ping DISCORD_OK`) have passed with Stage mirror; gateways include deterministic `/ping` / `/smoke`; LINE/WhatsApp runtime adapters and public webhook / long-running real-platform tests remain follow-up work |
| Adaptive Layout | Users can switch or auto-detect resolution / device / orientation to adjust every page | First version done for `/stage`, `/messenger`, `/admin`, `/admin/guide`, `/admin/structure`, `/admin/channels`, `/admin/models`, `/admin/openwebui`, and `/console` |
| Runtime Profiles | `/admin/models`, `/admin/voice-models`, and `/admin/live2d` manage LLM, STT/TTS, and Live2D separately; `/admin/characters` binds the character, and `/console` provides selected-session test overrides | Local version done; API keys are stored only in per-user secret files and are never returned in plaintext |
| Mobile | 390x844 / 430x932 / 360x800 / 768x1024 have no overlap | Chrome DevTools smoke done |
| iPhone | Safari login, mic, ASR, TTS, Live2D lip sync | Real-device pending |
| Android | Chrome login, mic, open mic, ASR, TTS, Live2D lip sync | Real-device pending |
| Regression | Full pytest | Done, latest `363 passed, 2 warnings` |

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

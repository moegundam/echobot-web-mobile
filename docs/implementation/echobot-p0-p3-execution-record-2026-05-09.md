# EchoBot P0-P3 Execution Record - 2026-05-09

## 中文版

### 範圍

本紀錄對應 2026-05-09 的 P0-P3 完成狀態。目標是把架構紀錄、Session 中心化整理、可自動化整合驗證、公開前安全檢查留下可追溯證據。

### 完成項目

| Priority | 狀態 | 結果 |
|---|---|---|
| P0 | 完成 | 新增架構與資料流文件：`docs/implementation/echobot-architecture-data-flow-2026-05-09.md`。 |
| P1 | 完成 | 新增 `SessionApplicationService`，讓 session router 變薄，session runtime 決策集中於 application service。 |
| P1 | 完成 | Console、Stage、Messenger、Admin 主要頁面已跑 browser smoke。 |
| P2 | 完成 | Live2D asset smoke 通過，確認 catalog、model3、motion、expression、Stage event binding 可用。 |
| P2 | 完成 | Open WebUI bridge smoke 通過，確認 narrow OpenAPI spec、sessions、stage event endpoint 可用。 |
| P2 | 完成 | Telegram local gateway smoke 通過，確認 inbound -> session history -> Stage replay 可用。 |
| P2 | 完成 | Discord local gateway smoke 通過，確認 inbound -> session history -> Stage replay 可用。 |
| P2 | 完成 | TTS smoke 通過，確認 `/api/web/tts` 能產生音訊 bytes。 |
| P3 | 完成 | `git diff --check` 通過。 |
| P3 | 完成 | `scripts/check_public_safety.py` 通過，未發現 tracked secret 或 `.echobot/` runtime 設定被追蹤。 |
| P3 | 完成 | Targeted pytest 通過。 |
| P3 | 完成 | Full pytest 已於本批次 P1 後通過。 |

### 重要提交

- `e8a92c6 Document architecture and data flows`
- `d126c48 Extract session application service`

### 驗證證據

```text
.venv/bin/python scripts/live2d_asset_smoke.py --base-url http://127.0.0.1:8001 --session-name p2-live2d-smoke
Live2D asset smoke passed.

.venv/bin/python scripts/openwebui_bridge_smoke.py --base-url http://127.0.0.1:8001 --token-file /tmp/echobot_openwebui_bridge_token --session-name p2-openwebui-smoke --target-user-id echobot-smoke@local
Open WebUI bridge smoke passed.

.venv/bin/python scripts/discord_gateway_smoke.py --base-url http://127.0.0.1:8001 --session-name p2-discord-smoke --text 'Reply exactly: DISCORD_OK' --timeout 120
Discord gateway smoke passed.

Telegram local gateway smoke:
Telegram gateway smoke passed.

TTS smoke:
status 200, provider edge, voice en-US-JennyNeural, audio bytes present.

.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001 --viewport 390x844 --viewport 768x1024 --viewport 1280x900
Browser smoke passed.

.venv/bin/python scripts/check_public_safety.py
Public safety check passed.

.venv/bin/python -m pytest tests/test_entrypoint_scripts.py tests/test_web_static.py tests/test_discord_channel.py tests/test_gateway.py -q
45 passed, 1 warning.

.venv/bin/python -m pytest
360 passed, 2 warnings.
```

### 邊界與保留項

- Console 的 runtime 操作仍應只影響目前測試/操作狀態，不應直接寫回 Admin 的永久模型、Voice、Live2D profile。
- Telegram/Discord local gateway smoke 已確認 EchoBot 內部 session routing 與 Stage replay；真正從手機或 Discord/Telegram client 發訊息到 bot 的驗收仍屬外部平台 E2E，可在需要時另外跑。
- Cloudflare Tunnel、Access、真機麥克風、Open WebUI 實機工作台連線屬部署環境驗收，不在本機無人工流程內假裝完成。

### 追加驗證：2026-05-09 20:55

本輪追加了可重跑的 Telegram gateway smoke 腳本，並修正 TG/DC smoke 對 deterministic `/ping` / `/smoke` command 的判定：這類 gateway command 會直接回覆並 mirror 到 Stage，不寫入一般 session history，因此 smoke 應驗證 Stage replay；一般文字訊息才驗證 session history。

```text
.venv/bin/python scripts/telegram_gateway_smoke.py --base-url http://127.0.0.1:8001 --session-name final-telegram-smoke --text '/ping TG_FINAL_OK' --timeout 120 --require-poller-running
Telegram gateway smoke passed.

.venv/bin/python scripts/discord_gateway_smoke.py --base-url http://127.0.0.1:8001 --session-name final-discord-smoke --text '/ping DISCORD_FINAL_OK' --timeout 120 --require-native-running
Discord gateway smoke passed.

.venv/bin/python scripts/echobot_entrypoint.py doctor
local_health: ok
remote_openwebui_reverse_health: ok
cloudflared_auth: warn - origin certificate is missing.

.venv/bin/python scripts/echobot_entrypoint.py smoke-openwebui --target local --session-name final-entrypoint-openwebui --target-user-id echobot-smoke@local
Open WebUI bridge smoke passed.

.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001 --viewport 360x800 --viewport 390x844 --viewport 768x1024 --viewport 1280x900
Browser smoke passed.

.venv/bin/python -m pytest tests/test_entrypoint_scripts.py tests/test_gateway.py -q
33 passed, 1 warning.
```

## English version

### Scope

This record captures the P0-P3 execution state for 2026-05-09. It preserves evidence for architecture documentation, session-centered cleanup, automatable integration checks, and public-readiness safety checks.

### Completed Items

| Priority | Status | Result |
|---|---|---|
| P0 | Done | Added architecture and data-flow documentation: `docs/implementation/echobot-architecture-data-flow-2026-05-09.md`. |
| P1 | Done | Added `SessionApplicationService` so the session router is thinner and session runtime decisions are centralized in the application service. |
| P1 | Done | Ran browser smoke over the main Console, Stage, Messenger, and Admin pages. |
| P2 | Done | Live2D asset smoke passed, covering catalog, model3, motion, expression, and Stage event binding. |
| P2 | Done | Open WebUI bridge smoke passed, covering the narrow OpenAPI spec, sessions, and stage event endpoint. |
| P2 | Done | Telegram local gateway smoke passed, covering inbound -> session history -> Stage replay. |
| P2 | Done | Discord local gateway smoke passed, covering inbound -> session history -> Stage replay. |
| P2 | Done | TTS smoke passed, confirming `/api/web/tts` returns audio bytes. |
| P3 | Done | `git diff --check` passed. |
| P3 | Done | `scripts/check_public_safety.py` passed, with no tracked secrets or tracked `.echobot/` runtime config found. |
| P3 | Done | Targeted pytest passed. |
| P3 | Done | Full pytest passed after the P1 service extraction. |

### Important Commits

- `e8a92c6 Document architecture and data flows`
- `d126c48 Extract session application service`

### Verification Evidence

```text
.venv/bin/python scripts/live2d_asset_smoke.py --base-url http://127.0.0.1:8001 --session-name p2-live2d-smoke
Live2D asset smoke passed.

.venv/bin/python scripts/openwebui_bridge_smoke.py --base-url http://127.0.0.1:8001 --token-file /tmp/echobot_openwebui_bridge_token --session-name p2-openwebui-smoke --target-user-id echobot-smoke@local
Open WebUI bridge smoke passed.

.venv/bin/python scripts/discord_gateway_smoke.py --base-url http://127.0.0.1:8001 --session-name p2-discord-smoke --text 'Reply exactly: DISCORD_OK' --timeout 120
Discord gateway smoke passed.

Telegram local gateway smoke:
Telegram gateway smoke passed.

TTS smoke:
status 200, provider edge, voice en-US-JennyNeural, audio bytes present.

.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001 --viewport 390x844 --viewport 768x1024 --viewport 1280x900
Browser smoke passed.

.venv/bin/python scripts/check_public_safety.py
Public safety check passed.

.venv/bin/python -m pytest tests/test_entrypoint_scripts.py tests/test_web_static.py tests/test_discord_channel.py tests/test_gateway.py -q
45 passed, 1 warning.

.venv/bin/python -m pytest
360 passed, 2 warnings.
```

### Boundaries And Remaining Manual Gates

- Console runtime changes should still affect only the current testing/operation state and must not directly overwrite Admin's persistent model, voice, or Live2D profiles.
- Telegram/Discord local gateway smoke verifies EchoBot's internal session routing and Stage replay. True platform E2E from a mobile Telegram or Discord client to the bot remains an external-platform acceptance check.
- Cloudflare Tunnel, Access, real-device microphone, and a real Open WebUI workstation connection are deployment-environment checks and are not claimed as complete by the local no-human flow.

### Follow-Up Verification: 2026-05-09 20:55

This round added a rerunnable Telegram gateway smoke script and fixed deterministic `/ping` / `/smoke` command handling in the TG/DC smoke scripts. These gateway commands reply directly and mirror to Stage without writing normal conversation history, so the smoke check should validate Stage replay for command messages and keep session-history validation for plain text messages.

```text
.venv/bin/python scripts/telegram_gateway_smoke.py --base-url http://127.0.0.1:8001 --session-name final-telegram-smoke --text '/ping TG_FINAL_OK' --timeout 120 --require-poller-running
Telegram gateway smoke passed.

.venv/bin/python scripts/discord_gateway_smoke.py --base-url http://127.0.0.1:8001 --session-name final-discord-smoke --text '/ping DISCORD_FINAL_OK' --timeout 120 --require-native-running
Discord gateway smoke passed.

.venv/bin/python scripts/echobot_entrypoint.py doctor
local_health: ok
remote_openwebui_reverse_health: ok
cloudflared_auth: warn - origin certificate is missing.

.venv/bin/python scripts/echobot_entrypoint.py smoke-openwebui --target local --session-name final-entrypoint-openwebui --target-user-id echobot-smoke@local
Open WebUI bridge smoke passed.

.venv/bin/python scripts/browser_smoke.py --base-url http://127.0.0.1:8001 --viewport 360x800 --viewport 390x844 --viewport 768x1024 --viewport 1280x900
Browser smoke passed.

.venv/bin/python -m pytest tests/test_entrypoint_scripts.py tests/test_gateway.py -q
33 passed, 1 warning.
```

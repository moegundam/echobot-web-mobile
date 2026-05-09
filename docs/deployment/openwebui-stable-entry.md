# EchoBot Open WebUI Stable Entrypoint

## 中文版

### 目標

這份文件記錄 EchoBot 本機服務與 Open WebUI bridge 的可重跑入口。它不取代 Cloudflare Tunnel；用途是讓本機開發與遠端 Open WebUI 測試不再依賴一次性的手動 `ssh -fN -R` 命令。

### 安全邊界

- 真實 token、API key、bot token 不寫入 repo。
- 本機 launchd runtime env 使用 gitignored 檔案，例如 `.env.launchd.local`。
- Open WebUI bridge token 建議放在 runtime-only token file，並由 launchd 讀取，不放在命令列。
- Cloudflare Tunnel + Access 仍是公開 HTTPS 與手機真機驗收的正式入口。

### 入口腳本

```shell
python scripts/echobot_entrypoint.py doctor
```

主要功能：

- 檢查 `.venv`、channel config、bridge token file、SSH、`cloudflared`、本機 health 與遠端 reverse health。
- 寫入 macOS launchd plists：
  - `com.moegundam.echobot.app`
  - `com.moegundam.echobot.openwebui-tunnel`（遠端 Open WebUI reverse tunnel label）
- 啟動、停止、查看 launchd 狀態。
- 透過本機或遠端 reverse tunnel 跑 Open WebUI bridge smoke。

### 建議本機流程

```shell
cp .env.local-tunnel.example .env.launchd.local

python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  write-launchd --component all

python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  start --component all --restart

python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  status
```

`.env.launchd.local` 必須保留在本機且不可提交。bridge token 應保留在 runtime-only token file，避免出現在 shell history。

### Open WebUI Bridge Smoke

```shell
python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  smoke-openwebui --target local --session-name demo
```

遠端 reverse tunnel 應從 Open WebUI 所在主機連回 `127.0.0.1:<remote-port>`，因此 smoke 必須在遠端主機視角執行：

```shell
python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  smoke-openwebui --target remote --session-name demo
```

### 狀態判斷

完成狀態應同時滿足：

- `launchctl print gui/$(id -u)/com.moegundam.echobot.app` 顯示 running。
- `launchctl print gui/$(id -u)/com.moegundam.echobot.openwebui-tunnel` 顯示 running（若使用遠端 reverse tunnel）。
- `curl http://127.0.0.1:8001/api/health` 回 `status=ok`。
- `python scripts/echobot_entrypoint.py smoke-openwebui --target local ...` 通過。
- `python scripts/echobot_entrypoint.py --remote-host user@your-openwebui-host smoke-openwebui --target remote ...` 通過（遠端 Open WebUI host 視角）。

### 未完成範圍

- Cloudflare named tunnel / DNS route / Access policy 尚未由本腳本建立。
- Open WebUI 後台 tool server 註冊仍需在 Open WebUI UI 或其持久化設定中完成。
- 手機真機 HTTPS 麥克風驗收另見 `docs/deployment/local-tunnel.md`。

## English version

### Goal

This document records the repeatable entrypoint for the local EchoBot service and the Open WebUI bridge. It does not replace Cloudflare Tunnel. It keeps local development and remote Open WebUI testing from depending on one-off manual `ssh -fN -R` commands.

### Security Boundary

- Real tokens, API keys, and bot tokens are not committed.
- The local launchd runtime env uses a gitignored file, for example `.env.launchd.local`.
- The Open WebUI bridge token should live in a runtime-only token file and be loaded by launchd, not placed on command lines.
- Cloudflare Tunnel + Access remains the formal HTTPS entrypoint for public testing and real mobile-device validation.

### Entrypoint Script

```shell
python scripts/echobot_entrypoint.py doctor
```

Main capabilities:

- Check `.venv`, channel config, bridge token file, SSH, `cloudflared`, local health, and remote reverse health.
- Write macOS launchd plists:
  - `com.moegundam.echobot.app`
  - `com.moegundam.echobot.openwebui-tunnel` (the remote Open WebUI reverse tunnel label)
- Start, stop, and inspect launchd status.
- Run Open WebUI bridge smoke through either the local endpoint or the remote reverse tunnel.

### Recommended Local Flow

```shell
cp .env.local-tunnel.example .env.launchd.local

python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  write-launchd --component all

python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  start --component all --restart

python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  status
```

`.env.launchd.local` must stay local and must not be committed. The bridge token should stay in a runtime-only token file so it does not appear in shell history.

### Open WebUI Bridge Smoke

```shell
python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  smoke-openwebui --target local --session-name demo
```

The remote reverse tunnel is reachable from the Open WebUI host as `127.0.0.1:<remote-port>`, so the smoke check must run from that host's point of view:

```shell
python scripts/echobot_entrypoint.py \
  --env-file .env.launchd.local \
  --token-file /path/to/runtime/bridge-token \
  --remote-host user@your-openwebui-host \
  smoke-openwebui --target remote --session-name demo
```

### Status Criteria

The entrypoint is complete when all of these pass:

- `launchctl print gui/$(id -u)/com.moegundam.echobot.app` shows running.
- `launchctl print gui/$(id -u)/com.moegundam.echobot.openwebui-tunnel` shows running when the remote reverse tunnel is used.
- `curl http://127.0.0.1:8001/api/health` returns `status=ok`.
- `python scripts/echobot_entrypoint.py smoke-openwebui --target local ...` passes.
- `python scripts/echobot_entrypoint.py --remote-host user@your-openwebui-host smoke-openwebui --target remote ...` passes from the remote Open WebUI host point of view.

### Not Covered

- This script does not create the Cloudflare named tunnel, DNS route, or Access policy.
- Open WebUI tool-server registration still has to be done in the Open WebUI UI or its persistent configuration.
- Real mobile-device HTTPS microphone validation is covered separately in `docs/deployment/local-tunnel.md`.

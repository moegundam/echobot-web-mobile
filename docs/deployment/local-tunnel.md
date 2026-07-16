# EchoBot Local Tunnel Deployment

## 中文版

### 目標

這份文件描述第一輪 10 人內測部署：EchoBot 在本機或 Mac 主機上執行，Cloudflare Tunnel 對外提供 HTTPS，Cloudflare Access 作為第一層登入與可信使用者來源。

本 profile 不把 EchoBot app 直接發布到 LAN。Cloudflare Tunnel 只連到 loopback ingress `127.0.0.1:8080`；EchoBot app 保持 container/internal `8000`，由 Nginx 先執行 body-size、rate 與 connection limits。

### 前置條件

- EchoBot source checkout；repo visibility 不得作為 secret protection
- Python 3.11+
- Cloudflare 帳號、已託管的 domain、可建立 named Tunnel
- `cloudflared` 已安裝並登入
- `.env.local-tunnel.example` 已複製成 `.env`

### 安裝

```shell
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.local-tunnel.example .env
```

填入 `.env` 的 LLM key，並保留內測安全預設：

```text
ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true
ECHOBOT_TRUSTED_USER_REQUIRED=true
ECHOBOT_TRUSTED_USER_HEADER=Cf-Access-Authenticated-User-Email
ECHOBOT_SHELL_SAFETY_MODE=workspace-write
ECHOBOT_WEB_PRIVATE_NETWORK_ENABLED=false
```

### 啟動 EchoBot 與 Ingress

建議使用 Compose；只有 Nginx ingress 對 host 發布 loopback port：

```shell
docker compose up --build --detach
curl --fail http://127.0.0.1:8080/healthz
```

開發者需要直接跑 Python 時，app 仍只聽 loopback，並另外啟動 `deploy/nginx/echobot.conf`：

```shell
source .venv/bin/activate
python -m echobot app --host 127.0.0.1 --port 8000
nginx -t -c "$(pwd)/deploy/nginx/echobot.conf"
nginx -c "$(pwd)/deploy/nginx/echobot.conf"
```

Local Tunnel profile 不使用 host `0.0.0.0`，也不把 app port `8000` 發布到 host。正式 tunnel route 必須指向 `http://127.0.0.1:8080`。

### Cloudflare Tunnel

建立 named tunnel：

```shell
cloudflared tunnel login
cloudflared tunnel create echobot-web-mobile
cloudflared tunnel route dns echobot-web-mobile echobot.example.com
```

複製範本：

```shell
mkdir -p ~/.cloudflared
cp docs/deployment/cloudflared-local-tunnel.example.yml ~/.cloudflared/echobot-web-mobile.yml
```

編輯 `~/.cloudflared/echobot-web-mobile.yml`，替換 tunnel、credentials-file 與 hostname。

驗證設定：

```shell
cloudflared tunnel --config ~/.cloudflared/echobot-web-mobile.yml ingress validate
cloudflared tunnel --config ~/.cloudflared/echobot-web-mobile.yml run echobot-web-mobile
```

### Cloudflare Access

在 Cloudflare Zero Trust 建立 Self-hosted application：

- Application domain：`https://echobot.example.com`
- Session duration：依內測需求設定，例如 24h
- Policy：只允許內測 10 人的 email 或 email domain
- Identity provider：使用你已配置的 Google、GitHub 或 One-time PIN

Access 必須注入預設 header：

```text
Cf-Access-Authenticated-User-Email
```

EchoBot 只信任這個由 Cloudflare Access 注入的 header。缺少或非法時，`/web`、`/api/*`、`/api/web/asr/ws` 都會拒絕。

### Health Check

本機未帶 trusted header 時，預期 401：

```shell
curl -i http://127.0.0.1:8080/api/health
```

通過 Cloudflare Access 登入後，瀏覽器開啟：

```text
https://echobot.example.com/web
```

WebSocket ASR route 必須走：

```text
wss://echobot.example.com/api/web/asr/ws
```

### 公開前安全檢查

後續每次上傳或設定公開前，先跑：

```shell
python scripts/check_public_safety.py
git status --short
```

檢查重點：

- `.echobot/`、`.env`、真實 bot token、OpenAI key、private key 不可被追蹤。
- 只有 `.env.*.example` 這類範本可以進 repo。
- channel token、Open WebUI bridge token、Cloudflare 設定值只留在本機 runtime 或部署 secret。

### Open WebUI Bridge Smoke

EchoBot 只提供窄 OpenAPI tool surface，不要把全站 `/openapi.json` 匯入 Open WebUI。

```shell
export ECHOBOT_OPENWEBUI_BRIDGE_TOKEN="<same value used by EchoBot>"
export ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS="tester@example.com"
python scripts/openwebui_bridge_smoke.py \
  --base-url http://127.0.0.1:8080 \
  --target-user-id tester@example.com \
  --session-name demo
```

具名 target 必須出現在 `ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS`；空白 allowlist 會 fail closed。只有明確設定 `ECHOBOT_OPENWEBUI_REQUIRE_TARGET_USER=false` 時才可省略 `--target-user-id` 並使用 shared root runtime，正式內測不建議這樣做。

### Discord Gateway

Discord 支援兩種模式：

- Protected webhook bridge：設定 `webhook_url` 與 `webhook_secret`，用 `/api/channels/discord/webhook` 做受控 inbound。
- Native bot events：設定 `bot_token`，安裝 `discord.py`，並在 Discord Developer Portal 開啟 Message Content Intent。

共享伺服器內測前務必設定 `allow_from`，避免任意 Discord 使用者寫入 session。

### Runtime Data

資料存放於：

```text
.echobot/users/<trusted-user-key>/
```

每個 Access 使用者各自擁有：

- sessions
- agent_sessions
- agent_traces
- attachments
- jobs
- cron
- runtime_settings
- Live2D uploads
- stage backgrounds

備份時至少保存 `.echobot/users/`，也建議保存 `.env` 的安全副本。

### Mobile Acceptance

必驗 viewport：

- `390x844`
- `430x932`
- `360x800`
- `768x1024`

必驗行為：

- iPhone Safari 可登入、開 `/web`、授權麥克風
- Android Chrome 可登入、錄音轉文字、常開麥、TTS 播放
- TTS 播放時 ASR 暫停，播放結束後恢復常開麥
- 切背景或鎖屏時停止錄音
- 停止語音只停止 TTS，不取消背景 Agent job

### 停止

```shell
# EchoBot: Ctrl-C
docker compose down
cloudflared tunnel cleanup echobot-web-mobile
```

`cleanup` 只清理 tunnel 連線狀態，不刪除 Cloudflare Access application 或 DNS route。

## English version

### Goal

This document describes the first 10-user testing deployment: EchoBot runs on a local host or Mac, Cloudflare Tunnel provides public HTTPS, and Cloudflare Access is the first login layer and trusted user source.

This profile does not publish the EchoBot application to the LAN. Cloudflare Tunnel connects only to the loopback ingress at `127.0.0.1:8080`; the application remains internal on port `8000`, behind Nginx body-size, rate, and connection limits.

### Prerequisites

- EchoBot source checkout; repository visibility is not a secret-control boundary
- Python 3.11+
- Cloudflare account, a managed domain, and permission to create a named Tunnel
- `cloudflared` installed and authenticated
- `.env.local-tunnel.example` copied to `.env`

### Install

```shell
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.local-tunnel.example .env
```

Fill in the LLM key in `.env`, and keep the testing safety defaults:

```text
ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true
ECHOBOT_TRUSTED_USER_REQUIRED=true
ECHOBOT_TRUSTED_USER_HEADER=Cf-Access-Authenticated-User-Email
ECHOBOT_SHELL_SAFETY_MODE=workspace-write
ECHOBOT_WEB_PRIVATE_NETWORK_ENABLED=false
```

### Start EchoBot And The Ingress

Compose is the recommended path. Only the Nginx ingress publishes a loopback host port:

```shell
docker compose up --build --detach
curl --fail http://127.0.0.1:8080/healthz
```

For direct Python development, keep the app on loopback and start the supplied Nginx configuration separately:

```shell
source .venv/bin/activate
python -m echobot app --host 127.0.0.1 --port 8000
nginx -t -c "$(pwd)/deploy/nginx/echobot.conf"
nginx -c "$(pwd)/deploy/nginx/echobot.conf"
```

The Local Tunnel profile does not publish a host `0.0.0.0` listener or the application port `8000`. The named Tunnel route must target `http://127.0.0.1:8080`.

### Cloudflare Tunnel

Create a named tunnel:

```shell
cloudflared tunnel login
cloudflared tunnel create echobot-web-mobile
cloudflared tunnel route dns echobot-web-mobile echobot.example.com
```

Copy the template:

```shell
mkdir -p ~/.cloudflared
cp docs/deployment/cloudflared-local-tunnel.example.yml ~/.cloudflared/echobot-web-mobile.yml
```

Edit `~/.cloudflared/echobot-web-mobile.yml`, replacing the tunnel, credentials-file, and hostname placeholders.

Validate the config:

```shell
cloudflared tunnel --config ~/.cloudflared/echobot-web-mobile.yml ingress validate
cloudflared tunnel --config ~/.cloudflared/echobot-web-mobile.yml run echobot-web-mobile
```

### Cloudflare Access

Create a Self-hosted application in Cloudflare Zero Trust:

- Application domain: `https://echobot.example.com`
- Session duration: set for testing needs, for example 24h
- Policy: allow only the 10 tester emails or email domain
- Identity provider: use your configured Google, GitHub, or One-time PIN provider

Access must inject the default header:

```text
Cf-Access-Authenticated-User-Email
```

EchoBot trusts only this Cloudflare Access-injected header. If the header is missing or invalid, `/web`, `/api/*`, and `/api/web/asr/ws` are rejected.

### Health Check

Without the trusted header locally, 401 is expected:

```shell
curl -i http://127.0.0.1:8080/api/health
```

After logging in through Cloudflare Access, open:

```text
https://echobot.example.com/web
```

The WebSocket ASR route must use:

```text
wss://echobot.example.com/api/web/asr/ws
```

### Pre-public Safety Check

For future pushes or before making the repository public, run:

```shell
python scripts/check_public_safety.py
git status --short
```

The check protects against:

- tracked `.echobot/`, `.env`, real bot tokens, OpenAI keys, or private keys
- tracked env files unless they are `.env.*.example` templates
- accidentally committing channel tokens, Open WebUI bridge tokens, or Cloudflare deployment values

### Open WebUI Bridge Smoke

EchoBot exposes only a narrow OpenAPI tool surface. Do not import the full site `/openapi.json` into Open WebUI.

```shell
export ECHOBOT_OPENWEBUI_BRIDGE_TOKEN="<same value used by EchoBot>"
export ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS="tester@example.com"
python scripts/openwebui_bridge_smoke.py \
  --base-url http://127.0.0.1:8080 \
  --target-user-id tester@example.com \
  --session-name demo
```

Every named target must appear in `ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS`; an empty allowlist fails closed. Omitting `--target-user-id` and using the shared root runtime is possible only when `ECHOBOT_OPENWEBUI_REQUIRE_TARGET_USER=false`, which is not recommended for private testing.

### Discord Gateway

Discord supports two modes:

- Protected webhook bridge: configure `webhook_url` and `webhook_secret`, then use `/api/channels/discord/webhook` for controlled inbound messages.
- Native bot events: configure `bot_token`, install `discord.py`, and enable Message Content Intent in the Discord Developer Portal.

Set `allow_from` before testing in shared servers so arbitrary Discord users cannot write into sessions.

### Runtime Data

Data is stored under:

```text
.echobot/users/<trusted-user-key>/
```

Each Access user gets isolated:

- sessions
- agent_sessions
- agent_traces
- attachments
- jobs
- cron
- runtime_settings
- Live2D uploads
- stage backgrounds

Backups should at least preserve `.echobot/users/`, and a secure copy of `.env` is also recommended.

### Mobile Acceptance

Required viewports:

- `390x844`
- `430x932`
- `360x800`
- `768x1024`

Required behavior:

- iPhone Safari can log in, open `/web`, and grant microphone access
- Android Chrome can log in, transcribe speech, use always-on mic, and play TTS
- ASR pauses during TTS playback and resumes always-on mic after playback
- Recording stops when the page goes to the background or the device locks
- Stop voice stops only TTS and does not cancel the background Agent job

### Stop

```shell
# EchoBot: Ctrl-C
docker compose down
cloudflared tunnel cleanup echobot-web-mobile
```

`cleanup` only clears tunnel connection state. It does not delete the Cloudflare Access application or DNS route.

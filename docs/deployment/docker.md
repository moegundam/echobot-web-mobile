# EchoBot Docker Deployment

## 中文版

這份文件說明 EchoBot Web Mobile 的第一版容器化打包方式。目標是把目前穩定的 Web / Stage / Messenger / Console / Admin runtime 包成單一 app container，方便本機、VPS、Cloudflare Tunnel 或後續 PWA/App 入口使用。

### 設計原則

- EchoBot container 只負責 app runtime，不內建 LLM、Open WebUI、Cloudflare Tunnel 或資料庫。
- `.echobot/` runtime data 使用 Docker volume 保存。
- API key、bot token、Open WebUI bridge token 只放在 `docker.env.local` 或外部 secret manager，不寫進 image。
- Compose 預設只綁 `127.0.0.1`，避免未經 reverse proxy / Access 保護就暴露到公開網路。
- HTTPS 由 Cloudflare Tunnel、Caddy、Nginx 或平台 ingress 提供；container 內只跑 HTTP。

### 檔案

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage Python runtime image |
| `.dockerignore` | 排除 `.env`、`.echobot`、venv、cache、docs/tests/scripts 等不必要 build context |
| `compose.yaml` | 單 container 本機/VPS compose profile |
| `docker.env.example` | 可複製成 `docker.env.local` 的非敏感範本 |

### 快速啟動

```shell
cp docker.env.example docker.env.local
docker compose build
docker compose up -d
curl -fsS http://127.0.0.1:8000/api/health
```

開啟：

```text
http://127.0.0.1:8000/console
http://127.0.0.1:8000/stage?session_name=demo
http://127.0.0.1:8000/messenger
http://127.0.0.1:8000/admin
```

### 設定模型

`docker.env.local` 只放本機或部署環境的 secret，不要 commit。

```text
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=your-model
LLM_API_KEY=your-api-key
```

也可以改接 LiteLLM、Ollama 或 vLLM 的 OpenAI-compatible endpoint：

```text
LLM_BASE_URL=http://host.docker.internal:4000/v1
LLM_MODEL=your-local-model
LLM_API_KEY=your-local-provider-key
```

### 安全預設

Compose 預設包含：

- `127.0.0.1:${ECHOBOT_HOST_PORT:-8000}:8000`
- `read_only: true`
- `tmpfs: /tmp`
- `cap_drop: [ALL]`
- `security_opt: no-new-privileges:true`
- `ECHOBOT_SHELL_SAFETY_MODE=workspace-write`
- named volume `echobot_data:/app/.echobot`

如果要給手機或外部網路使用，請使用 Cloudflare Tunnel / Caddy / Nginx 提供 HTTPS，不要直接把 `0.0.0.0:8000` 匿名暴露到公網。

### 維護命令

```shell
docker compose ps
docker compose logs -f echobot
docker compose exec echobot python -m echobot --help
docker compose down
```

保留資料但重建 image：

```shell
docker compose build --pull
docker compose up -d
```

刪除 runtime volume 會移除 session/history/attachments，除非已備份，否則不要執行：

```shell
docker compose down -v
```

### 已知邊界

- v1 不把 LLM 模型權重包進 image。
- v1 不內建 Postgres；目前仍使用 `.echobot` file-backed runtime。
- v1 不內建 HTTPS；手機麥克風測試仍需要外層 HTTPS。
- Docker daemon 未啟動時，`docker build` / `docker compose up` 無法本機驗證，只能先跑靜態檢查與 CI。

## English version

This document describes the first Docker packaging profile for EchoBot Web Mobile. The goal is to package the stable Web / Stage / Messenger / Console / Admin runtime as one app container for local use, VPS use, Cloudflare Tunnel, or future PWA/App entrypoints.

### Design Principles

- The EchoBot container runs only the app runtime. It does not bundle an LLM, Open WebUI, Cloudflare Tunnel, or a database.
- `.echobot/` runtime data is persisted through a Docker volume.
- API keys, bot tokens, and Open WebUI bridge tokens belong in `docker.env.local` or an external secret manager, never in the image.
- Compose binds to `127.0.0.1` by default so the app is not exposed before a reverse proxy / Access layer is configured.
- HTTPS is provided by Cloudflare Tunnel, Caddy, Nginx, or platform ingress. The container serves HTTP internally.

### Files

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage Python runtime image |
| `.dockerignore` | Excludes `.env`, `.echobot`, venv, caches, docs/tests/scripts, and other unnecessary build context |
| `compose.yaml` | Single-container local/VPS compose profile |
| `docker.env.example` | Non-sensitive template copied to `docker.env.local` |

### Quick Start

```shell
cp docker.env.example docker.env.local
docker compose build
docker compose up -d
curl -fsS http://127.0.0.1:8000/api/health
```

Open:

```text
http://127.0.0.1:8000/console
http://127.0.0.1:8000/stage?session_name=demo
http://127.0.0.1:8000/messenger
http://127.0.0.1:8000/admin
```

### Model Configuration

`docker.env.local` is for local or deployment secrets. Do not commit it.

```text
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=your-model
LLM_API_KEY=your-api-key
```

LiteLLM, Ollama, or vLLM can be used through an OpenAI-compatible endpoint:

```text
LLM_BASE_URL=http://host.docker.internal:4000/v1
LLM_MODEL=your-local-model
LLM_API_KEY=your-local-provider-key
```

### Security Defaults

Compose includes:

- `127.0.0.1:${ECHOBOT_HOST_PORT:-8000}:8000`
- `read_only: true`
- `tmpfs: /tmp`
- `cap_drop: [ALL]`
- `security_opt: no-new-privileges:true`
- `ECHOBOT_SHELL_SAFETY_MODE=workspace-write`
- named volume `echobot_data:/app/.echobot`

For mobile or internet access, put Cloudflare Tunnel / Caddy / Nginx in front and provide HTTPS. Do not anonymously expose `0.0.0.0:8000` to the public internet.

### Maintenance Commands

```shell
docker compose ps
docker compose logs -f echobot
docker compose exec echobot python -m echobot --help
docker compose down
```

Rebuild while keeping runtime data:

```shell
docker compose build --pull
docker compose up -d
```

Removing the runtime volume deletes sessions, history, and attachments. Do not run this without a backup:

```shell
docker compose down -v
```

### Known Boundaries

- v1 does not bundle LLM weights into the image.
- v1 does not include Postgres; the runtime remains `.echobot` file-backed.
- v1 does not include HTTPS; real mobile microphone tests still need an outer HTTPS layer.
- If the Docker daemon is not running, `docker build` / `docker compose up` cannot be validated locally; use static checks and CI first.

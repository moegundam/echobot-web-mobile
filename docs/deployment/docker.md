# EchoBot Docker Deployment

## 中文版

這份文件說明 EchoBot Web Mobile 的容器化打包方式。Compose 由 loopback Nginx ingress 與內部 EchoBot app 兩個 service 組成，讓 request-size、rate 與 stream connection 限制在 request 進入 FastAPI parser 前生效。

### 設計原則

- EchoBot container 只負責 app runtime，不內建 LLM、Open WebUI、Cloudflare Tunnel 或資料庫。
- 使用 immutable digest 的 Chainguard Nginx ingress 是唯一 host-published service；EchoBot `8000` 只暴露在 Compose network。
- Nginx 透過 Docker embedded DNS 每 5 秒重新解析 `echobot` service；app container 被替換且 IP 改變時，不需要重啟 ingress。
- ingress healthcheck 會實際請求 `http://127.0.0.1:8080/healthz`，不是只執行設定語法檢查。
- `.echobot/` runtime data 使用 Docker volume 保存。
- API key、bot token、Open WebUI bridge token 只放在 `docker.env.local` 或外部 secret manager，不寫進 image。
- Compose ingress 預設只綁 `127.0.0.1:8080`，避免未經 reverse proxy / Access 保護就暴露到公開網路。
- 本維護流程只在指定的外部 Mac mini Docker server 建置、執行與掃描 image；一般工作站只做 source/test/docs。
- HTTPS 由 Cloudflare Tunnel、Caddy、Nginx 或平台 ingress 提供；container 內只跑 HTTP。

### 檔案

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage Python runtime image |
| `.dockerignore` | 排除 `.env`、`.echobot`、venv、cache、docs/tests/scripts 等不必要 build context |
| `compose.yaml` | 本地 build 的 ingress + app Compose profile |
| `compose.production.yaml` | 強制 digest-qualified GHCR image 的 production profile |
| `deploy/nginx/echobot-container.conf` | Container ingress resource policy |
| `docker.env.example` | 可複製成 `docker.env.local` 的非敏感範本 |

### 快速啟動

```shell
cp docker.env.example docker.env.local
docker compose build
docker compose up -d
curl -fsS http://127.0.0.1:8080/healthz
```

### 使用已發佈 image

`main` 分支會把 image 發佈到你自己的 GitHub Container Registry：

```text
ghcr.io/moegundam/echobot-web-mobile:upgrade
ghcr.io/moegundam/echobot-web-mobile:latest
ghcr.io/moegundam/echobot-web-mobile:sha-<commit>
```

開發/測試可直接拉取 immutable SHA tag；正式部署必須使用 registry 回報的 digest：

```shell
docker login ghcr.io
docker pull ghcr.io/moegundam/echobot-web-mobile:sha-<commit>
```

私有 package 建議使用只有 `read:packages` 的 GitHub token，並以 `--password-stdin` 登入；不要把 token 寫進 shell history 或 repo。

Production profile 不接受 mutable tag：

```shell
cp docker.env.example docker.env.local
# 編輯 docker.env.local：
# ECHOBOT_IMAGE_SHA256=<64-character digest value without sha256:>
# ECHOBOT_ADMIN_ALLOWLIST=admin@example.com
# ECHOBOT_OPERATOR_ALLOWLIST=operator@example.com
docker compose --env-file docker.env.local -f compose.production.yaml config
docker compose --env-file docker.env.local -f compose.production.yaml up -d
curl -fsS http://127.0.0.1:8080/healthz
```

Production profile 會要求可信 proxy assertion；loopback 只用於 `/healthz`。不要透過 `http://127.0.0.1:8080` 開啟受保護頁面，因為直接請求沒有 Cloudflare Access identity，正確結果是 `401`。登入 Access 後由 HTTPS hostname 開啟：

```text
https://echobot.example.com/console
https://echobot.example.com/stage?session_name=demo
https://echobot.example.com/messenger
https://echobot.example.com/admin
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

### Runtime 模式與 GPU/CUDA 策略

目前 Docker image 是 `app-only` runtime：它負責 EchoBot Web、Stage、Messenger、Console、Admin、session 與 gateway，不把 LLM 權重或 CUDA runtime 包進 image。

建議模式：

| Mode | 用途 | 設定方式 |
|---|---|---|
| `app-only` | 最輕量、最容易維護的預設容器 | EchoBot container 只跑 app；LLM/ASR/TTS 走預設或外部 provider |
| `external-provider-only` | GB10 / GPU 主機 / Open WebUI / LiteLLM / Ollama / vLLM | 將 `LLM_BASE_URL`、`ECHOBOT_TTS_OPENAI_BASE_URL`、`ECHOBOT_ASR_OPENAI_BASE_URL` 指到外部 OpenAI-compatible endpoint |
| `local-onnx-cpu` | 小規模本機語音測試 | 使用 `sherpa-sense-voice`、`silero`、`kokoro`，預設 provider 仍是 `cpu` |

若要做 NVIDIA CUDA 最佳化，請把 GPU inference 放在獨立服務或外部主機上，再讓 EchoBot 透過 OpenAI-compatible API 呼叫。對 DGX Spark / GB10 類環境，優先使用官方支援的 ARM64 / NVIDIA Container Runtime / NGC 或對應 provider stack；不要把目前這個 EchoBot web container 改成混合 CUDA image，否則 image 會變大、維護面會變複雜，且前台/中台/後台 runtime 會跟模型服務耦合。

私有模型下載鏡像站預設被封鎖，避免 SSRF 或誤打內網端點。只有在你明確管理該 artifact host 時才開：

```text
ECHOBOT_TTS_KOKORO_ALLOW_PRIVATE_DOWNLOAD=true
ECHOBOT_ASR_SHERPA_ALLOW_PRIVATE_DOWNLOAD=true
ECHOBOT_VAD_SILERO_ALLOW_PRIVATE_DOWNLOAD=true
```

### 安全預設

Compose 預設包含：

- ingress：`127.0.0.1:${ECHOBOT_HOST_PORT:-8080}:8080`
- app：只使用 `expose: 8000`，不 publish host port
- route-specific request-size、rate 與 SSE connection limits
- Docker DNS app replacement recovery 與 HTTP live healthcheck
- app 與 ingress 兩個映像都在 CI 產生 SBOM，並以 Trivy `HIGH` / `CRITICAL` 零容忍門檻阻擋發布
- `read_only: true`
- `tmpfs: /tmp`
- `cap_drop: [ALL]`
- `security_opt: no-new-privileges:true`
- `ECHOBOT_SHELL_SAFETY_MODE=workspace-write`
- named volume `echobot_data:/app/.echobot`

如果要給手機或外部網路使用，請讓 Cloudflare Tunnel / Caddy 連到 loopback ingress `127.0.0.1:8080` 並提供 HTTPS，不要直接 publish app port 或匿名暴露到公網。

### 維護命令

```shell
docker compose ps
docker compose logs -f ingress echobot
docker compose exec echobot python -m echobot --help
docker compose down
```

保留資料但重建 image：

```shell
docker compose build --pull
docker compose up -d
```

備份 named volume 中的 runtime data：

```shell
mkdir -p backups
docker compose cp echobot:/app/.echobot ./backups/echobot-data
```

確認備份可讀後再進行破壞性維護。`docker.env.local` 含 secrets，需另存於 Git 以外的權限受控位置。

刪除 runtime volume 會移除 session/history/attachments，除非已備份，否則不要執行：

```shell
docker compose down -v
```

### 已知邊界

- v1 不把 LLM 模型權重包進 image。
- v1 不內建 Postgres；目前仍使用 `.echobot` file-backed runtime。
- v1 不內建 HTTPS；手機麥克風測試仍需要外層 HTTPS。
- 本維護流程不在一般工作站啟動 Docker daemon；container build/runtime/scan 由指定外部 Docker host 與 CI 驗證。

## English version

This document describes the EchoBot Web Mobile container profile. Compose uses a loopback Nginx ingress plus an internal EchoBot app service so request-size, rate, and stream-connection controls run before the FastAPI request parser.

### Design Principles

- The EchoBot container runs only the app runtime. It does not bundle an LLM, Open WebUI, Cloudflare Tunnel, or a database.
- A digest-pinned Chainguard Nginx ingress is the only host-published service. EchoBot port `8000` is exposed only inside the Compose network.
- Nginx re-resolves the `echobot` service through Docker's embedded DNS every five seconds, so an app replacement with a new IP does not require an ingress restart.
- The ingress healthcheck performs a live request to `http://127.0.0.1:8080/healthz`; it is not limited to configuration syntax validation.
- `.echobot/` runtime data is persisted through a Docker volume.
- API keys, bot tokens, and Open WebUI bridge tokens belong in `docker.env.local` or an external secret manager, never in the image.
- Compose ingress binds to `127.0.0.1:8080` by default so the app is not exposed before a reverse proxy / Access layer is configured.
- The maintainer workflow builds, runs, and scans images only on the designated external Mac mini Docker server; normal workstations handle source, tests, and docs.
- HTTPS is provided by Cloudflare Tunnel, Caddy, Nginx, or platform ingress. The container serves HTTP internally.

### Files

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage Python runtime image |
| `.dockerignore` | Excludes `.env`, `.echobot`, venv, caches, docs/tests/scripts, and other unnecessary build context |
| `compose.yaml` | Local-build ingress + app Compose profile |
| `compose.production.yaml` | Production profile requiring a digest-qualified GHCR image |
| `deploy/nginx/echobot-container.conf` | Container ingress resource policy |
| `docker.env.example` | Non-sensitive template copied to `docker.env.local` |

### Quick Start

```shell
cp docker.env.example docker.env.local
docker compose build
docker compose up -d
curl -fsS http://127.0.0.1:8080/healthz
```

### Using The Published Image

The `main` branch publishes the image to your own GitHub Container Registry:

```text
ghcr.io/moegundam/echobot-web-mobile:upgrade
ghcr.io/moegundam/echobot-web-mobile:latest
ghcr.io/moegundam/echobot-web-mobile:sha-<commit>
```

Development and test environments may pull an immutable SHA tag. Production must use the registry-reported digest:

```shell
docker login ghcr.io
docker pull ghcr.io/moegundam/echobot-web-mobile:sha-<commit>
```

For a private package, use a GitHub token limited to `read:packages` and pass it through `--password-stdin`. Never put the token in shell history or the repository.

The production profile rejects mutable tags:

```shell
cp docker.env.example docker.env.local
# Edit docker.env.local:
# ECHOBOT_IMAGE_SHA256=<64-character digest value without sha256:>
# ECHOBOT_ADMIN_ALLOWLIST=admin@example.com
# ECHOBOT_OPERATOR_ALLOWLIST=operator@example.com
docker compose --env-file docker.env.local -f compose.production.yaml config
docker compose --env-file docker.env.local -f compose.production.yaml up -d
curl -fsS http://127.0.0.1:8080/healthz
```

The production profile requires a trusted proxy assertion; loopback is only for `/healthz`. Do not open protected pages through `http://127.0.0.1:8080`, because direct requests have no Cloudflare Access identity and correctly return `401`. After Access login, use the HTTPS hostname:

```text
https://echobot.example.com/console
https://echobot.example.com/stage?session_name=demo
https://echobot.example.com/messenger
https://echobot.example.com/admin
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

### Runtime Modes And GPU/CUDA Strategy

The current Docker image is an `app-only` runtime. It runs EchoBot Web, Stage, Messenger, Console, Admin, sessions, and gateways. It does not bundle LLM weights or a CUDA runtime into the image.

Recommended modes:

| Mode | Purpose | Configuration |
|---|---|---|
| `app-only` | Smallest and easiest-to-maintain default container | EchoBot runs only the app; LLM/ASR/TTS use default or external providers |
| `external-provider-only` | GB10 / GPU host / Open WebUI / LiteLLM / Ollama / vLLM | Point `LLM_BASE_URL`, `ECHOBOT_TTS_OPENAI_BASE_URL`, and `ECHOBOT_ASR_OPENAI_BASE_URL` at external OpenAI-compatible endpoints |
| `local-onnx-cpu` | Small local speech testing | Use `sherpa-sense-voice`, `silero`, and `kokoro`; the default execution provider remains `cpu` |

For NVIDIA CUDA optimization, keep GPU inference in a separate service or external host, then call it from EchoBot through an OpenAI-compatible API. On DGX Spark / GB10-style environments, prefer officially supported ARM64 / NVIDIA Container Runtime / NGC or matching provider stacks. Do not turn this EchoBot web container into a mixed CUDA image unless you intentionally accept a larger image, more maintenance, and tighter coupling between the web runtime and model serving.

Private model download mirrors are blocked by default to avoid SSRF and accidental internal-network access. Enable them only for artifact hosts you explicitly control:

```text
ECHOBOT_TTS_KOKORO_ALLOW_PRIVATE_DOWNLOAD=true
ECHOBOT_ASR_SHERPA_ALLOW_PRIVATE_DOWNLOAD=true
ECHOBOT_VAD_SILERO_ALLOW_PRIVATE_DOWNLOAD=true
```

### Security Defaults

Compose includes:

- ingress: `127.0.0.1:${ECHOBOT_HOST_PORT:-8080}:8080`
- app: `expose: 8000` only, with no host-published app port
- route-specific request-size, rate, and SSE connection limits
- Docker DNS app-replacement recovery and an HTTP live healthcheck
- separate app and ingress SBOMs plus zero-tolerance Trivy `HIGH` / `CRITICAL` publication gates in CI
- `read_only: true`
- `tmpfs: /tmp`
- `cap_drop: [ALL]`
- `security_opt: no-new-privileges:true`
- `ECHOBOT_SHELL_SAFETY_MODE=workspace-write`
- named volume `echobot_data:/app/.echobot`

For mobile or internet access, point Cloudflare Tunnel / Caddy at the loopback ingress `127.0.0.1:8080` and provide HTTPS. Do not publish the app port or expose it anonymously.

### Maintenance Commands

```shell
docker compose ps
docker compose logs -f ingress echobot
docker compose exec echobot python -m echobot --help
docker compose down
```

Rebuild while keeping runtime data:

```shell
docker compose build --pull
docker compose up -d
```

Back up runtime data from the named volume:

```shell
mkdir -p backups
docker compose cp echobot:/app/.echobot ./backups/echobot-data
```

Verify that the backup is readable before destructive maintenance. `docker.env.local` contains secrets and must be stored separately in access-controlled storage outside Git.

Removing the runtime volume deletes sessions, history, and attachments. Do not run this without a backup:

```shell
docker compose down -v
```

### Known Boundaries

- v1 does not bundle LLM weights into the image.
- v1 does not include Postgres; the runtime remains `.echobot` file-backed.
- v1 does not include HTTPS; real mobile microphone tests still need an outer HTTPS layer.
- The maintainer workflow does not start Docker on normal workstations; container build/runtime/scan runs on the designated external Docker host and in CI.

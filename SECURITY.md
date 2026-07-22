# Security Policy

## 中文版

### 支援範圍

本 repo 是 EchoBot Web/Mobile 管理版的開發來源。公開展示或 10 人內測前，請使用經當次 CI、security scan 與部署驗收通過的 `main` commit 或正式 release；不要依賴舊 feature branch 名稱。

### 回報安全問題

請不要在公開 issue 中貼出 API key、Cloudflare token、Open WebUI bridge token、bot token、session history、attachments 或 `.echobot/users/` 內容。

建議回報內容：

- 受影響的 route、API 或功能。
- 是否需要登入或 trusted user header。
- 最小重現步驟。
- 預期行為與實際行為。
- 風險分類，例如資料外洩、越權、XSS、SSRF、任意檔案讀寫、工具權限提升或 denial of service。

若 repo 已公開，請使用 [GitHub Security Advisory](https://github.com/moegundam/echobot-web-mobile/security/advisories/new) 私下回報，不要先建立公開 issue 或公開 exploit 細節。

### 公開部署安全基準

公開服務或 10 人內測前至少要符合：

1. 使用 HTTPS，手機麥克風功能不得走明文 HTTP。
2. 使用 Cloudflare Access 或可信 reverse proxy auth。
3. Tunnel/production profile 至少啟用以下 fail-closed 設定，並把範例 email 換成真實管理員：
   - `ECHOBOT_DEPLOYMENT_PROFILE=tunnel`
   - `ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true`
   - `ECHOBOT_TRUSTED_USER_REQUIRED=true`
   - `ECHOBOT_TRUSTED_USER_ASSERTION_REQUIRED=true`
   - `ECHOBOT_ADMIN_ALLOWLIST=admin@example.com`
   - `ECHOBOT_ADMIN_REQUIRED=true`
4. 不匿名公開 `/admin`、`/docs`、`/redoc`、`/openapi.json` 或 `/api/*`。
5. `ECHOBOT_SHELL_SAFETY_MODE` 預設使用 `workspace-write` 或 `read-only`。
6. Open WebUI bridge 必須設定強隨機 `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN`。
7. Messenger 與外部通訊平台 gateway 預設維持 `chat_only`。
8. Secrets 不進 repo，也不顯示在 UI 或 logs。
9. `.echobot/users/<user_id>/...` 必須維持 user namespace 隔離。
10. 上線前要跑 `python -m pytest`，並完成手機 viewport smoke test。

### Secrets

禁止提交：

- LLM / TTS / ASR API keys。
- Cloudflare account token、tunnel credentials、Access secrets。
- Open WebUI bridge token。
- Telegram、LINE、Discord、WhatsApp、QQ bot token 或 client secret。
- `.env`、`.echobot/`、session history、attachments、local model credentials。

### 風險接受

此專案包含 Agent tools、檔案操作、網路請求、ASR/TTS 與外部 provider。若要公開成匿名 SaaS，需要額外加入正式帳號系統、rate limiting、audit logs、approval gate、provider data policy、abuse monitoring 與更完整的 sandbox。

## English version

### Supported Scope

This repository is the development source for the EchoBot Web/Mobile management edition. For public demos or 10-user testing, use a specific `main` commit or release that passed the current CI, security scan, and deployment acceptance; do not rely on an old feature-branch name.

### Reporting Security Issues

Do not post API keys, Cloudflare tokens, Open WebUI bridge tokens, bot tokens, session history, attachments, or `.echobot/users/` contents in public issues.

Useful report contents:

- Affected route, API, or feature.
- Whether login or a trusted user header is required.
- Minimal reproduction steps.
- Expected and actual behavior.
- Risk category, such as data exposure, authorization bypass, XSS, SSRF, arbitrary file read/write, tool privilege escalation, or denial of service.

If the repository is public, use a [GitHub Security Advisory](https://github.com/moegundam/echobot-web-mobile/security/advisories/new) for private disclosure. Do not open a public issue or publish exploit details first.

### Public Deployment Security Baseline

Before exposing the service publicly or to a 10-user test, require at least:

1. HTTPS. Mobile microphone features must not use plaintext HTTP.
2. Cloudflare Access or trusted reverse proxy authentication.
3. For Tunnel/production profiles, enable at least these fail-closed settings and replace the example email with the real administrator:
   - `ECHOBOT_DEPLOYMENT_PROFILE=tunnel`
   - `ECHOBOT_TRUSTED_USER_HEADER_ENABLED=true`
   - `ECHOBOT_TRUSTED_USER_REQUIRED=true`
   - `ECHOBOT_TRUSTED_USER_ASSERTION_REQUIRED=true`
   - `ECHOBOT_ADMIN_ALLOWLIST=admin@example.com`
   - `ECHOBOT_ADMIN_REQUIRED=true`
4. Do not anonymously expose `/admin`, `/docs`, `/redoc`, `/openapi.json`, or `/api/*`.
5. Use `workspace-write` or `read-only` as the default `ECHOBOT_SHELL_SAFETY_MODE`.
6. Set a strong random `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN`.
7. Keep Messenger and external channel gateways in `chat_only` mode by default.
8. Keep secrets out of the repository, UI, and logs.
9. Preserve `.echobot/users/<user_id>/...` namespace isolation.
10. Run `python -m pytest` and complete a mobile viewport smoke test before release.

### Secrets

Never commit:

- LLM / TTS / ASR API keys.
- Cloudflare account tokens, tunnel credentials, or Access secrets.
- Open WebUI bridge token.
- Telegram, LINE, Discord, WhatsApp, QQ bot tokens or client secrets.
- `.env`, `.echobot/`, session history, attachments, or local model credentials.

### Accepted Risk

This project includes Agent tools, file operations, network requests, ASR/TTS, and external providers. Turning it into an anonymous public SaaS requires additional account management, rate limiting, audit logs, approval gates, provider data policy, abuse monitoring, and stronger sandboxing.

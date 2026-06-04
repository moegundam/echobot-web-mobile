# EchoBot Security Scan Record - 2026-06-02

## 中文版

### 目標

對 `echobot-web-mobile` 做公開前安全性原始碼、供應鏈與容器掃描。完成標準是：選定掃描工具沒有未處理的中風險以上結果、修補後已重跑驗證、Docker 掃描與建置都在外部 mini Docker server 執行。

### 範圍與邊界

- Repo：`echobot-web-mobile`
- 分支：`main`
- 掃描基準：`e98f6eb Publish Docker image to GHCR` 之後的本次工作樹
- Docker 目標：外部 mini Docker server `<external-docker-host>`
- 遠端工作目錄：`<remote-scan-workdir>`
- 本機只做原始碼編輯、pytest、py_compile、public-safety scan 與紀錄；不在本機安裝或執行 Docker 容器。
- 同步到遠端掃描副本時排除 `.git/`、`.venv/`、`.uv-cache/`、`.echobot/`、`.env*`、`docker.env.local`、cache 與 build 產物。
- 不提交 `.echobot/`、本機 `.env`、token、API key 或原始敏感掃描輸出。

### 掃描工具

| 類別 | 工具 | 執行位置 | Final gate |
|---|---|---|---|
| Python SAST | Bandit `1.9.4` | `<external-docker-host>` | Medium+ = 0 |
| SAST | Semgrep OSS `p/default` | `<external-docker-host>` | WARNING/ERROR findings = 0 |
| Secret scan | Gitleaks `8.30.1` | `<external-docker-host>` | Findings = 0 |
| GitHub Actions audit | zizmor `1.25.2` | `<external-docker-host>` | Findings = 0 |
| Filesystem / dependency / config / secret | Trivy `0.71.0` fs | `<external-docker-host>` | Vulns/misconfigs/secrets = 0 |
| Container image | Trivy `0.71.0` image | `<external-docker-host>` | Vulns/misconfigs/secrets = 0 |
| Dependency audit | pip-audit | `<external-docker-host>` | No known vulnerable requirements when available |
| Repo public safety | `scripts/check_public_safety.py` | 本機 | Pass |
| Regression | pytest | 本機 | Pass |
| Container runtime | Docker health smoke | `<external-docker-host>` | `/api/health` 200 |

### 主要修補

| 類別 | 修補 |
|---|---|
| Unsafe archive extraction | 新增 `safe_extract_tar()`，拒絕 path traversal 與逃出目的地的 symlink/hardlink，再用於 SenseVoice ASR 與 Kokoro TTS model extraction。 |
| Dynamic URL / SSRF | 新增 centralized HTTP URL validation；預設拒絕 non-HTTP(S)、loopback、link-local、private IP literal、`localhost`、`.local`、單段內網 host、常見 metadata host，並封鎖解析到 private/non-global IP 的 DNS 名稱；OpenAI-compatible provider 明確 opt-in private URL 以保留 LiteLLM/Ollama/vLLM 本地模型流程。 |
| XML parsing | Office redline helpers/validators 改用 `defusedxml.ElementTree`。 |
| Weak hash warning | Channel route digest 保留相容 SHA1，但標示 `usedforsecurity=False` 並只作 stable route suffix，不作安全決策。 |
| GitHub Actions | `actions/checkout` pin SHA，並設定 `persist-credentials: false`。 |
| Container CVE | Dockerfile 改用 pinned Wolfi base digest，保留 Python 3.12 runtime，nonroot `65532:65532`，image 掃描降為 0 medium+。 |
| Vulnerable memory stack | 預設 `requirements.txt` 移除目前有 medium+/critical CVE 的 `agentscope` / `reme-ai[light]` transitive stack；保留 runtime fallback，`requirements-memory.txt` 暫停列出套件直到上游修補。 |
| Runtime dependency | 將 FastAPI upload route 需要的 `python-multipart` 加為直接核心 dependency，不再依賴 transitive install。 |
| Local cache exposure | `.uv-cache/` 加入 `.gitignore` 與 public-safety forbidden path。 |
| Secret handling | launchd token/log path 從 `/tmp` 改到 `~/.echobot/`，避免 shared temp path。 |

### Final5 結果

遠端報告目錄：`<remote-scan-workdir>/reports`

| Gate | Report | Result |
|---|---|---|
| Docker compose config | `docker-compose-config-final5.txt` | exit `0` |
| Docker build | `docker-build-final5.log` / `docker-image-final5.txt` | exit `0`, image size `123167984` bytes |
| Docker health smoke | `docker-smoke-final5b-health.json` | exit `0`, `/api/health` returned `200` |
| Bandit | `bandit-final5.json` | exit `0`, medium+ results `0` |
| Semgrep | `semgrep-final5.json` | exit `0`, WARNING/ERROR findings `0` |
| Gitleaks | `gitleaks-final5.json` | exit `0`, findings `0` |
| zizmor | `zizmor-final5.json` | exit `0`, findings `0` |
| Trivy fs | `trivy-fs-final5.json` | exit `0`, vulns `0`, misconfigs `0`, secrets `0` |
| Trivy image | `trivy-image-final5.json` | exit `0`, vulns `0`, misconfigs `0`, secrets `0` |
| pip-audit | `pip-audit-final5.json` | exit `0`, vulns `0` |
| Public safety | local command | pass |
| py_compile | local command | pass |
| pytest | local command | `370 passed`, 2 warnings |

### 已知環境觀察

- `<external-docker-host>` 登入 banner 顯示大量 zombie processes。這是外部 Docker host 維運風險，不是 EchoBot 原始碼 findings；本次未清理主機，避免擴大任務範圍。
- Docker health smoke 使用 dummy `LLM_API_KEY=EMPTY` 與不可用 loopback LLM endpoint，只驗證 app startup 與 `/api/health`，沒有發模型請求，也沒有將 dummy env 寫入 repo。
- ReMe/AgentScope memory stack 目前暫停放入預設 dependency set；若未來要恢復，必須先確認上游固定版本經 Trivy/pip-audit 掃描沒有 medium+。

## English version

### Goal

Run pre-publication source-code, supply-chain, and container security scans for `echobot-web-mobile`. The completion standard is: selected scanners report no unhandled medium-or-higher risk, remediations are re-verified, and Docker scanning/building is performed on the external mini Docker server only.

### Scope And Boundaries

- Repo: `echobot-web-mobile`
- Branch: `main`
- Scan baseline: the current worktree after `e98f6eb Publish Docker image to GHCR`
- Docker target: external mini Docker server `<external-docker-host>`
- Remote work directory: `<remote-scan-workdir>`
- Local machine is used only for source edits, pytest, py_compile, public-safety scan, and record keeping; no Docker containers are installed or executed locally.
- Remote scan sync excludes `.git/`, `.venv/`, `.uv-cache/`, `.echobot/`, `.env*`, `docker.env.local`, caches, and build outputs.
- Do not commit `.echobot/`, local `.env`, tokens, API keys, or raw sensitive scanner output.

### Scanner Set

| Category | Tool | Execution Target | Final gate |
|---|---|---|---|
| Python SAST | Bandit `1.9.4` | `<external-docker-host>` | Medium+ = 0 |
| SAST | Semgrep OSS `p/default` | `<external-docker-host>` | WARNING/ERROR findings = 0 |
| Secret scan | Gitleaks `8.30.1` | `<external-docker-host>` | Findings = 0 |
| GitHub Actions audit | zizmor `1.25.2` | `<external-docker-host>` | Findings = 0 |
| Filesystem / dependency / config / secret | Trivy `0.71.0` fs | `<external-docker-host>` | Vulns/misconfigs/secrets = 0 |
| Container image | Trivy `0.71.0` image | `<external-docker-host>` | Vulns/misconfigs/secrets = 0 |
| Dependency audit | pip-audit | `<external-docker-host>` | No known vulnerable requirements when available |
| Repo public safety | `scripts/check_public_safety.py` | Local | Pass |
| Regression | pytest | Local | Pass |
| Container runtime | Docker health smoke | `<external-docker-host>` | `/api/health` 200 |

### Main Remediations

| Category | Remediation |
|---|---|
| Unsafe archive extraction | Added `safe_extract_tar()`, blocking path traversal and escaping symlink/hardlink targets before extraction; wired into SenseVoice ASR and Kokoro TTS model extraction. |
| Dynamic URL / SSRF | Added centralized HTTP URL validation; by default blocks non-HTTP(S), loopback, link-local, private IP literals, `localhost`, `.local`, single-label intranet hosts, common metadata hosts, and DNS names that resolve to private/non-global IPs. OpenAI-compatible providers explicitly opt into private URLs to preserve LiteLLM/Ollama/vLLM local model workflows. |
| XML parsing | Switched Office redline helpers/validators to `defusedxml.ElementTree`. |
| Weak hash warning | Kept SHA1 channel route digest for compatibility, marked `usedforsecurity=False`, and kept it only as a stable route suffix, not as a security decision. |
| GitHub Actions | Pinned `actions/checkout` by SHA and set `persist-credentials: false`. |
| Container CVE | Migrated Dockerfile to a pinned Wolfi base digest, kept Python 3.12 runtime, used nonroot `65532:65532`, and reduced image scan findings to 0 medium+. |
| Vulnerable memory stack | Removed the current medium+/critical-CVE `agentscope` / `reme-ai[light]` transitive stack from default `requirements.txt`; preserved runtime fallback, and kept `requirements-memory.txt` disabled until upstream publishes fixed packages. |
| Runtime dependency | Added `python-multipart` as a direct core dependency for FastAPI upload routes instead of relying on transitive installation. |
| Local cache exposure | Added `.uv-cache/` to `.gitignore` and public-safety forbidden paths. |
| Secret handling | Moved launchd token/log paths from `/tmp` to `~/.echobot/`, avoiding shared temp paths. |

### Final5 Results

Remote report directory: `<remote-scan-workdir>/reports`

| Gate | Report | Result |
|---|---|---|
| Docker compose config | `docker-compose-config-final5.txt` | exit `0` |
| Docker build | `docker-build-final5.log` / `docker-image-final5.txt` | exit `0`, image size `123167984` bytes |
| Docker health smoke | `docker-smoke-final5b-health.json` | exit `0`, `/api/health` returned `200` |
| Bandit | `bandit-final5.json` | exit `0`, medium+ results `0` |
| Semgrep | `semgrep-final5.json` | exit `0`, WARNING/ERROR findings `0` |
| Gitleaks | `gitleaks-final5.json` | exit `0`, findings `0` |
| zizmor | `zizmor-final5.json` | exit `0`, findings `0` |
| Trivy fs | `trivy-fs-final5.json` | exit `0`, vulns `0`, misconfigs `0`, secrets `0` |
| Trivy image | `trivy-image-final5.json` | exit `0`, vulns `0`, misconfigs `0`, secrets `0` |
| pip-audit | `pip-audit-final5.json` | exit `0`, vulns `0` |
| Public safety | local command | pass |
| py_compile | local command | pass |
| pytest | local command | `370 passed`, 2 warnings |

### Known Environment Observations

- The `<external-docker-host>` login banner reports many zombie processes. This is an external Docker host operations risk, not an EchoBot source finding; host cleanup was intentionally not performed to avoid expanding scope.
- Docker health smoke used dummy `LLM_API_KEY=EMPTY` plus an unreachable loopback LLM endpoint. It verified app startup and `/api/health` only, made no model request, and did not write dummy env values into the repo.
- The ReMe/AgentScope memory stack is currently disabled in the default dependency set. If it is restored later, fixed upstream versions must first pass Trivy/pip-audit with no medium+ findings.

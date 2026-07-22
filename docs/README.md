# EchoBot Documentation Index

## 中文版

### 使用方式

這是公開 repo 文件的唯一入口。請先依文件狀態選擇：

- **目前可操作**：描述現行程式與可直接執行的步驟；變更程式時必須同步更新。
- **參考/規劃**：描述可選架構、遷移路徑或尚未全部接線的能力，不代表已部署完成。
- **歷史紀錄**：保留特定日期的稽核或執行證據；不能用來宣稱目前版本已通過。

### 目前可操作

| 分類 | 文件 | 用途 |
|---|---|---|
| 部署 | [Local Tunnel](./deployment/local-tunnel.md) | Compose / Python、Cloudflare Access、健康檢查、備份與停止 |
| 部署 | [Docker](./deployment/docker.md) | 本機 image、GHCR production profile、volume 與安全預設 |
| 整合 | [Open WebUI stable entry](./deployment/openwebui-stable-entry.md) | Narrow bridge 的固定入口與 smoke |
| 網站 | [Web site structure](./implementation/echobot-web-site-structure.md) | Stage、Messenger、Console、Admin 與 API 邊界 |
| 網站 | [Web page links](./implementation/echobot-web-page-links.md) | 可檢查的頁面清單 |
| 架構 | [Stage event broker](./architecture/stage-event-broker.md) | user/session scope、memory/Redis 邊界 |
| 資料 | [Session store backends](./database/session-store-backends.md) | JSONL / SQLite repository 行為 |
| 安全 | [Secret storage](./security/secret-storage.md) | secret 的位置、遮罩、遷移與禁止事項 |
| 安全 | [Container vulnerability policy](./security/container-vulnerability-policy.md) | SBOM、Trivy 與 exception gate |

### 參考/規劃

| 分類 | 文件 | 邊界 |
|---|---|---|
| 資料庫 | [PostgreSQL migration](./database/postgresql-migration.md) | production migration 設計；完成 runtime cutover 前不是現行 store |
| 產品整合 | [Web/Mobile integration plan](./implementation/echobot-web-mobile-integration-plan.md) | 原始整合規劃；以現行 README/API 為準 |
| 參考專案 | [Open-LLM-VTuber gap](./implementation/open-llm-vtuber-reference-gap.md) | 借鑑方向，不代表搬入其 backend |

### 歷史工程紀錄

以下文件是日期型 snapshot，只能用來追溯當時觀察：

- [Architecture and data flow, 2026-05-09](./implementation/echobot-architecture-data-flow-2026-05-09.md)
- [P0–P3 execution record, 2026-05-09](./implementation/echobot-p0-p3-execution-record-2026-05-09.md)
- [Architecture/code/CUDA audit, 2026-06-02](./architecture/echobot-architecture-code-cuda-audit-2026-06-02.md)
- [Security scan record, 2026-06-02](./security/echobot-security-scan-record-2026-06-02.md)
- [Modular runtime foundation, 2026-07-20](./architecture/modular-runtime-foundation-2026-07-20.md)
- [Modular API review, 2026-07-20](./architecture/modular-api-review-2026-07-20.md)

### 文件檢查

```shell
.venv/bin/python scripts/validate_documentation.py --repo-docs docs --check
```

檢查會驗證本索引涵蓋所有公開 Markdown、相對連結可解析，且不會修改檔案。敏感資料仍另跑 `python scripts/check_public_safety.py`。

## English version

### How To Use This Index

This is the single entrypoint for public repository documentation. Choose documents by status:

- **Current operation**: describes the current implementation and executable steps; update it with behavior changes.
- **Reference/planning**: describes optional architecture, migration paths, or incomplete wiring; it is not deployment evidence.
- **Historical record**: preserves an audit or execution snapshot for a date; it cannot prove the current version passed.

### Current Operation

| Category | Document | Purpose |
|---|---|---|
| Deployment | [Local Tunnel](./deployment/local-tunnel.md) | Compose / Python, Cloudflare Access, health, backup, and shutdown |
| Deployment | [Docker](./deployment/docker.md) | Local image, GHCR production profile, volumes, and security defaults |
| Integration | [Open WebUI stable entry](./deployment/openwebui-stable-entry.md) | Stable narrow-bridge entrypoint and smoke |
| Web | [Web site structure](./implementation/echobot-web-site-structure.md) | Stage, Messenger, Console, Admin, and API boundaries |
| Web | [Web page links](./implementation/echobot-web-page-links.md) | Reviewable page inventory |
| Architecture | [Stage event broker](./architecture/stage-event-broker.md) | User/session scope and memory/Redis boundaries |
| Data | [Session store backends](./database/session-store-backends.md) | JSONL / SQLite repository behavior |
| Security | [Secret storage](./security/secret-storage.md) | Secret locations, masking, migration, and prohibitions |
| Security | [Container vulnerability policy](./security/container-vulnerability-policy.md) | SBOM, Trivy, and exception gates |

### Reference / Planning

| Category | Document | Boundary |
|---|---|---|
| Database | [PostgreSQL migration](./database/postgresql-migration.md) | Production migration design; not the active store before runtime cutover |
| Product integration | [Web/Mobile integration plan](./implementation/echobot-web-mobile-integration-plan.md) | Original integration plan; current README/API behavior takes precedence |
| Reference project | [Open-LLM-VTuber gap](./implementation/open-llm-vtuber-reference-gap.md) | Borrowed design direction, not an imported backend |

### Historical Engineering Records

These dated files are snapshots for traceability only:

- [Architecture and data flow, 2026-05-09](./implementation/echobot-architecture-data-flow-2026-05-09.md)
- [P0–P3 execution record, 2026-05-09](./implementation/echobot-p0-p3-execution-record-2026-05-09.md)
- [Architecture/code/CUDA audit, 2026-06-02](./architecture/echobot-architecture-code-cuda-audit-2026-06-02.md)
- [Security scan record, 2026-06-02](./security/echobot-security-scan-record-2026-06-02.md)
- [Modular runtime foundation, 2026-07-20](./architecture/modular-runtime-foundation-2026-07-20.md)
- [Modular API review, 2026-07-20](./architecture/modular-api-review-2026-07-20.md)

### Documentation Check

```shell
.venv/bin/python scripts/validate_documentation.py --repo-docs docs --check
```

The check verifies complete public Markdown indexing and resolvable relative links without modifying files. Run `python scripts/check_public_safety.py` separately for sensitive-data checks.

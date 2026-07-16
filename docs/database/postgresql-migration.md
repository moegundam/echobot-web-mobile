# EchoBot PostgreSQL Migration Foundation

## 中文版

### 目前能力

| 項目 | 狀態 | 說明 |
|---|---|---|
| Schema v2 | 已實作 | transaction、migration ledger、可重複執行的 enum/table/index DDL、Session channel binding 唯一索引 |
| Tenant key | 已實作 | tenant table 使用 `(owner_user_id, id)` 主鍵與同範圍外鍵 |
| Session data | 已建模 | Session、current pointer、ordered messages、attachments、jobs、cron、traces |
| Runtime documents | 已建模 | 保留 file-backed JSON store 的 lossless migration landing area |
| Seed export v2 | 已實作 | root + 所有 user namespace、counts、SHA-256、附件 manifest、遞迴 secret redaction |
| Dry run | 已實作 | 驗證來源與 digest，不寫入輸出檔 |
| PostgreSQL importer | 尚未實作 | 目前不可宣稱已完成 DB backfill/parity |
| Runtime adapter | 尚未實作 | production runtime 仍使用 `.echobot/` file-backed stores |
| Backup/restore drill | 尚未實作 | PostgreSQL 切換前的必要 gate |

### 指令

輸出 schema：

```bash
python -m echobot db schema --output /tmp/echobot-schema.sql
```

只驗證 migration seed，不寫檔：

```bash
python -m echobot db export --workspace . --dry-run
```

輸出通過驗證的 seed：

```bash
python -m echobot db export \
  --workspace . \
  --output /tmp/echobot-pg-seed.json
```

### Seed v2 範圍

- `.echobot/` root scope，owner key 為 `default`。
- `.echobot/users/<storage-key>/` 的所有 user scope。
- conversation sessions、agent sessions 與 current pointers。
- LLM、Voice、Live2D、Character、runtime、jobs、cron、delivery、route-session JSON stores。
- Agent trace JSONL records。
- Attachment metadata、實際檔案大小與 SHA-256；不把二進位內容嵌入 JSON。

### 安全與失敗規則

- 專用 secret files 不在 allowlist 內，不會匯出。
- 名稱含 token、secret、password、API key、credential、authorization、cookie、private key 或 webhook URL 的欄位會清空，只保留 configured 狀態。
- JSON/JSONL 損壞、附件遺失或 attachment path 越界會寫入 `manifest.invalid_records`。
- 有 invalid record 時，`--dry-run` 回非零；正式 export 拒絕建立輸出檔。
- Seed 包含對話、prompt、trace 與附件 metadata，仍屬敏感資料，不可提交到 repo。
- v2 會檢查既有核心資料表是否使用 `(owner_user_id, id)` 複合主鍵。若偵測到舊版單欄 `id` 主鍵，transaction 會中止且不寫入 v2 migration ledger。
- 舊版 schema 不做原地自動改寫。先輸出並驗證 migration seed，再匯入全新的 schema-v2 database；importer 完成前不可把此流程視為 production cutover。

### 切換 PostgreSQL 前的 Gate

1. 實作 transactional、idempotent importer。
2. 驗證 entity counts、message ordering、references 與 digest parity。
3. 實作 file/PostgreSQL 共用 repository contracts 與 runtime selector。
4. 在兩種 backend 跑完整 regression。
5. 完成 backup、clean-target restore 與 rollback drill。
6. 完成 secret manager 決策；migration seed 永遠不搬移 secret value。

## English version

### Current Capability

| Item | Status | Detail |
|---|---|---|
| Schema v2 | Implemented | Transaction, migration ledger, rerunnable enum/table/index DDL, and a unique Session channel-binding index |
| Tenant key | Implemented | Tenant tables use `(owner_user_id, id)` keys and tenant-scoped foreign keys |
| Session data | Modeled | Sessions, current pointers, ordered messages, attachments, jobs, cron, and traces |
| Runtime documents | Modeled | Lossless landing area for file-backed JSON stores |
| Seed export v2 | Implemented | Root plus all user namespaces, counts, digest, attachment manifest, recursive secret redaction |
| Dry run | Implemented | Validates source records and digest without writing output |
| PostgreSQL importer | Not implemented | Database backfill/parity is not yet a supported claim |
| Runtime adapter | Not implemented | Production runtime remains file-backed under `.echobot/` |
| Backup/restore drill | Not implemented | Required before a PostgreSQL cutover |

### Commands

```bash
python -m echobot db schema --output /tmp/echobot-schema.sql
python -m echobot db export --workspace . --dry-run
python -m echobot db export --workspace . --output /tmp/echobot-pg-seed.json
```

### Seed v2 Coverage

- Root `.echobot/` scope as owner `default` and every `.echobot/users/<storage-key>/` scope.
- Conversation and agent Sessions with current pointers.
- LLM, Voice, Live2D, Character, runtime, jobs, cron, delivery, and route-session JSON stores.
- Agent trace JSONL records.
- Attachment metadata, actual size, and SHA-256 without embedded binary content.

### Safety And Failure Rules

- Dedicated secret files are outside the export allowlist.
- Secret-bearing field names are cleared and expose only configured state.
- Corrupt JSON/JSONL, missing attachments, and escaping attachment paths become manifest validation errors.
- Invalid input makes dry-run return nonzero and blocks output-file creation.
- The seed still contains sensitive conversations, prompts, traces, and attachment metadata; never commit it to the repository.
- v2 verifies that existing core tables use the `(owner_user_id, id)` composite primary key. A legacy single-column `id` schema aborts the transaction without recording the v2 migration.
- Legacy schemas are not rewritten in place. Export and validate a migration seed, then import it into a fresh schema-v2 database; this is not a production cutover until the importer exists and passes the gates below.

### Cutover Gates

Implement a transactional idempotent importer, count/reference/order/digest parity, shared file/PostgreSQL repository contracts, dual-backend regression, backup/restore/rollback drills, and a secret-manager decision before switching runtime storage. Secret values must never be moved through the migration seed.

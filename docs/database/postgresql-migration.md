# EchoBot PostgreSQL Migration Start

## 中文版

這份文件記錄 PostgreSQL 化的第一步。現階段 EchoBot runtime 仍維持 `.echobot/` file-backed 儲存，避免打斷既有本機開發與內測流程；本批次先加入可重複產生的 PostgreSQL schema 草案與非敏感 migration seed 匯出。

### 指令

輸出 schema：

```bash
python -m echobot db schema --output /tmp/echobot-schema.sql
```

匯出目前 `.echobot/` 狀態為 migration seed：

```bash
python -m echobot db export --workspace . --output /tmp/echobot-pg-seed.json
```

### 安全規則

- 匯出檔不包含 API key、bot token、webhook secret 或 client secret 明文。
- migration seed 只作為後續 PostgreSQL adapter/backfill 的輸入。
- 真正切換到 PostgreSQL 前，需要再加入 DB adapter、連線設定、dual-write 或 backfill 驗證。

## English version

This document records the first PostgreSQL migration step. EchoBot still uses the `.echobot/` file-backed runtime store in this phase so local development and private testing keep working. This batch adds a repeatable PostgreSQL schema draft and a non-sensitive migration seed export.

### Commands

Write the schema:

```bash
python -m echobot db schema --output /tmp/echobot-schema.sql
```

Export the current `.echobot/` state as a migration seed:

```bash
python -m echobot db export --workspace . --output /tmp/echobot-pg-seed.json
```

### Security Rules

- The export does not include plaintext API keys, bot tokens, webhook secrets, or client secrets.
- The migration seed is only input for a future PostgreSQL adapter/backfill.
- Before switching runtime storage to PostgreSQL, add the DB adapter, connection settings, and dual-write or backfill verification.

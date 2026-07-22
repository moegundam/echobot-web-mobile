# EchoBot Session Store Backends

## 中文版

### Backend 選擇

| Backend | 狀態 | 儲存位置 | 適用情境 |
|---|---|---|---|
| `jsonl` | 預設、相容路徑 | `.echobot/sessions/*.jsonl`、`.echobot/agent_sessions/*.jsonl` | 本機開發、低複雜度部署 |
| `sqlite` | opt-in、已實作 | `.echobot/sessions.sqlite3`、`.echobot/agent_sessions.sqlite3` | 單 process transaction/WAL |
| PostgreSQL | 後續 production path | 由 migration seed/importer 決定 | runtime adapter/importer 尚未完成 |

### RuntimeOptions 與 CLI

- `RuntimeOptions.session_store_backend` 預設 `jsonl`。
- `RuntimeOptions.agent_session_store_backend` 可單獨指定；未指定時跟隨主要 Session backend。
- interactive CLI、gateway 與 app 共用 runtime argument parser：

```bash
.venv/bin/python -m echobot chat --session-store-backend jsonl
.venv/bin/python -m echobot chat --session-store-backend sqlite
.venv/bin/python -m echobot chat \
  --session-store-backend sqlite \
  --agent-session-store-backend jsonl
```

- CLI choices 目前只有 `jsonl` 與 `sqlite`；未知值會拒絕。
- API app 的 `RuntimeOptions` 由建立 app 的 caller 注入；目前沒有已確認的 `.env` selector，不新增未實作的 env 名稱。

### SQLite 行為

- 使用 Python standard library `sqlite3`，不新增 ORM dependency。
- 啟用 WAL 與 busy timeout。
- session、message、metadata、current pointer、ToolCall 等資料在 transaction 內處理。
- migration 以 JSONL store 讀取來源、以 `SQLiteSessionStore` 寫入目標。
- migration 不覆蓋既有 SQLite rows；相同 fingerprint 會計為 skipped，不同內容會列為 conflict。
- pointer 只有在 target 尚無 pointer 且 source session 可用時才遷移。
- migration 失敗會 rollback，並回傳 `MigrationReport`。
- SQLite store 支援 `close()`；runtime shutdown 會關閉持有資源的 repository。

### JSONL -> SQLite migration

目前 source 提供 module CLI：

```bash
.venv/bin/python -m echobot.runtime.session_migration \
  .echobot/sessions \
  .echobot/sessions.sqlite3
```

若要遷移 agent sessions，另外執行：

```bash
.venv/bin/python -m echobot.runtime.session_migration \
  .echobot/agent_sessions \
  .echobot/agent_sessions.sqlite3
```

驗證順序：

1. 備份 `.echobot/`，保留 JSONL 原始來源。
2. 執行 migration，檢查 `migrated`、`skipped`、`conflicts`、`errors` 與 `pointer_migrated`。
3. 有 `errors` 或未解決 `conflicts` 時，不切換 runtime backend。
4. 使用 `--session-store-backend sqlite` 做 smoke，再做完整 regression。
5. rollback 時改回 `--session-store-backend jsonl`；不要刪除 SQLite 或 JSONL。

### PostgreSQL migration boundary

- PostgreSQL schema 與 seed export 位於 `echobot/persistence/` 與 `echobot/cli/db.py`。
- export 可選 JSONL 或 SQLite session source；它是 private migration seed，不是 runtime switch。
- JSONL seed：

```bash
.venv/bin/python -m echobot db export \
  --workspace . \
  --output /tmp/echobot-pg-seed.json
```

- CLI 可用 `--session-store-backend sqlite` 選擇 workspace 內的 SQLite store，也可用 `--sqlite-source` 明確指定 SQLite storage root 或 `sessions.sqlite3`。選擇 SQLite 後不會 fallback 或混入 JSONL。

```bash
.venv/bin/python -m echobot db export \
  --workspace . \
  --session-store-backend sqlite \
  --sqlite-source .echobot \
  --output /tmp/echobot-pg-seed.json
```
- seed 會排除 dedicated secret files、清理 secret-bearing fields，且不嵌入 attachment bytes；conversation、prompt、trace 與 attachment metadata 仍是敏感資料。
- PostgreSQL importer、runtime adapter、counts/reference/digest parity、backup/restore drill 尚未完成，不能把 seed export 當成 PostgreSQL cutover。

### Operational verification

```bash
.venv/bin/python -m pytest tests/test_session_repository.py tests/test_session_migration.py
.venv/bin/python -m pytest tests/test_persistence_export.py tests/test_app_api.py
.venv/bin/python -m pytest
git diff --check
```

SQLite file check：

```bash
sqlite3 .echobot/sessions.sqlite3 'PRAGMA journal_mode; PRAGMA busy_timeout;'
```

預期 journal mode 是 `wal`；busy timeout 應為正值。若本機沒有 `sqlite3` CLI，改用 repository tests 驗證。

### 相容與限制

- JSONL 是 rollback 基線；SQLite opt-in 不代表已完成 PostgreSQL production migration。
- Session backend 是 process-local repository 選擇；它不提供跨多 worker 的 Stage event delivery。多 worker Stage 仍須 Redis broker。
- SQLite 適合單 process/單 host；不要把同一 SQLite database 當成多 host shared store。
- 不會自動刪除 legacy JSONL，也不會在 migration 過程中搬移 secrets。

## English version

### Backend Selection

| Backend | Status | Storage | Use |
|---|---|---|---|
| `jsonl` | Default, compatibility path | `.echobot/sessions/*.jsonl`, `.echobot/agent_sessions/*.jsonl` | Local development and simple deployments |
| `sqlite` | Implemented opt-in | `.echobot/sessions.sqlite3`, `.echobot/agent_sessions.sqlite3` | Single-process transactional storage |
| PostgreSQL | Later production path | Determined by seed/importer | Runtime adapter and importer are not implemented |

### RuntimeOptions And CLI

- `RuntimeOptions.session_store_backend` defaults to `jsonl`.
- `RuntimeOptions.agent_session_store_backend` can be selected independently and otherwise follows the main backend.
- The shared CLI parser accepts:

```bash
.venv/bin/python -m echobot chat --session-store-backend jsonl
.venv/bin/python -m echobot chat --session-store-backend sqlite
.venv/bin/python -m echobot chat --session-store-backend sqlite --agent-session-store-backend jsonl
```

- Supported CLI choices are `jsonl` and `sqlite`.
- The app receives `RuntimeOptions` from its caller. There is no verified `.env` selector for this backend, so do not invent one.

### SQLite Behavior

- SQLite uses the Python standard library, WAL, and a busy timeout.
- Session, message, metadata, current-pointer, and ToolCall writes use transactions.
- Migration does not overwrite existing rows; identical fingerprints are skipped and different rows are reported as conflicts.
- A current pointer is migrated only when the target has no pointer and the source session exists.
- Failures roll back and are returned through `MigrationReport`.
- Resource-owning SQLite stores expose `close()`, and runtime shutdown closes them.

### JSONL To SQLite Migration

The current source provides this module command:

```bash
.venv/bin/python -m echobot.runtime.session_migration .echobot/sessions .echobot/sessions.sqlite3
.venv/bin/python -m echobot.runtime.session_migration .echobot/agent_sessions .echobot/agent_sessions.sqlite3
```

Keep the JSONL source, inspect the migration report, resolve errors/conflicts, then smoke-test SQLite before selecting it. Roll back by selecting JSONL again; do not delete either store during comparison.

### PostgreSQL Boundary

- PostgreSQL schema and seed export live under `echobot/persistence/` and `echobot/cli/db.py`.
- The export is a private migration seed, not a runtime switch:

```bash
.venv/bin/python -m echobot db export --workspace . --output /tmp/echobot-pg-seed.json
```

- The CLI supports `--session-store-backend sqlite` for the workspace store and `--sqlite-source` for an explicit SQLite storage root or `sessions.sqlite3`. SQLite selection never falls back to or merges JSONL.

```bash
.venv/bin/python -m echobot db export --workspace . \
  --session-store-backend sqlite --sqlite-source .echobot \
  --output /tmp/echobot-pg-seed.json
```
- Dedicated secret files and secret-bearing fields are excluded or redacted. Conversation, prompt, trace, and attachment metadata remain sensitive.
- Importer, runtime adapter, parity checks, and backup/restore drills are not implemented; do not treat seed export as a PostgreSQL cutover.

### Operational Verification

```bash
.venv/bin/python -m pytest tests/test_session_repository.py tests/test_session_migration.py
.venv/bin/python -m pytest tests/test_persistence_export.py tests/test_app_api.py
.venv/bin/python -m pytest
git diff --check
```

Use `sqlite3 .echobot/sessions.sqlite3 'PRAGMA journal_mode; PRAGMA busy_timeout;'` when the local CLI is installed; otherwise rely on repository tests.

### Compatibility And Limitations

- JSONL is the rollback baseline; SQLite opt-in is not PostgreSQL production migration.
- The session backend is process-local and does not provide cross-worker Stage delivery. Multi-worker Stage still requires Redis.
- SQLite is intended for a single process/host and is not a shared multi-host store.
- Migration does not delete legacy JSONL or move secrets.

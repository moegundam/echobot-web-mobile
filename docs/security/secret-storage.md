# EchoBot Secret Storage

## 中文版

### 能力矩陣

| 類型 | 目前來源 | 明文是否回傳 API | 寫入方式 | 現況 |
|---|---|---:|---|---|
| Open WebUI bridge token | `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN` 或同名 `_FILE` | 否 | deployment environment / mounted file | `Done`；兩個來源同時存在會 fail closed |
| Telegram bot token | `.echobot/channel_secrets.json` | 否 | 原子 replace、mode `0600` | `Done` |
| Discord bot/webhook credentials | `.echobot/channel_secrets.json` | 否 | 原子 replace、mode `0600` | `Done` |
| QQ client secret | `.echobot/channel_secrets.json` | 否 | 原子 replace、mode `0600` | `Done` |
| LLM / Voice profile API key | per-user `*_secrets.json` | 否 | local restricted file | `Partial`；尚未全部改用共用 SecretStore adapter |
| External Vault/KMS/Keychain | 尚未選定 | 不適用 | 尚未實作 | `Planned` |

### Channel credential 遷移

1. `channels.json` 只保留非敏感設定與空白 secret 欄位。
2. 舊版 inline secret 仍可讀取。
3. 下一次由 API 或 runtime 儲存設定時，secret 會寫入同目錄的 `channel_secrets.json`。
4. 新 secret snapshot 驗證完成後才原子替換，檔案權限固定為 `0600`。
5. inline 與 secret store 同時存在但值不同時，載入會拒絕，錯誤訊息不包含任一 secret。

### 操作規則

- 不提交 `.env`、`.echobot/`、`channel_secrets.json`、bot token、API key 或 bridge token。
- Container secret 優先使用 mounted file 與 `_FILE` 變數；不要把值寫進 image layer 或 Compose YAML。
- API/UI 只顯示 `*_configured`、來源類型或版本等非敏感 metadata。
- Character package 與 PostgreSQL migration seed 不包含 secret value。
- Secret 被貼到聊天、log、issue 或 Git history 時，刪檔不等於撤銷；必須向 provider 旋轉/重發。

### 尚未完成

- 尚未選定 production Vault/KMS/Keychain provider。
- 尚未實作 provider-neutral rotation/revocation workflow。
- LLM/Voice profile secrets 尚待遷移到同一個 SecretStore contract。
- 尚未完成 backup/restore 時 secret reference 與 provider version 的一致性驗收。

## English version

### Capability Matrix

| Secret type | Current source | Returned by API | Write path | Status |
|---|---|---:|---|---|
| Open WebUI bridge token | `ECHOBOT_OPENWEBUI_BRIDGE_TOKEN` or matching `_FILE` | No | deployment environment / mounted file | `Done`; dual sources fail closed |
| Telegram bot token | `.echobot/channel_secrets.json` | No | atomic replace, mode `0600` | `Done` |
| Discord bot/webhook credentials | `.echobot/channel_secrets.json` | No | atomic replace, mode `0600` | `Done` |
| QQ client secret | `.echobot/channel_secrets.json` | No | atomic replace, mode `0600` | `Done` |
| LLM / Voice profile API key | per-user `*_secrets.json` | No | restricted local file | `Partial`; not all paths use the shared SecretStore adapter |
| External Vault/KMS/Keychain | not selected | Not applicable | not implemented | `Planned` |

### Channel Credential Migration

`channels.json` keeps non-sensitive configuration only. Legacy inline secrets remain readable and move to `channel_secrets.json` on the next save. The replacement snapshot is fully validated before an atomic `0600` write. Conflicting inline and stored values fail closed without including either value in the error.

### Operating Rules

- Never commit `.env`, `.echobot/`, `channel_secrets.json`, bot tokens, API keys, or bridge tokens.
- Prefer mounted files plus `_FILE` variables for container secrets; never bake values into image layers or Compose YAML.
- APIs and UI expose configured state and non-sensitive metadata only.
- Character packages and PostgreSQL migration seeds never contain secret values.
- A value exposed to chat, logs, issues, or Git history must be rotated at the provider; deleting a file does not revoke it.

### Remaining Work

Select a production Vault/KMS/Keychain provider, implement provider-neutral rotation/revocation, move all LLM/Voice profile secrets behind the shared contract, and prove backup/restore parity for secret references and provider versions.

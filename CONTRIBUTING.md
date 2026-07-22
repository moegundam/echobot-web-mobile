# Contributing

## 中文版

### 開發原則

本 repo 目前優先服務 EchoBot Web/Mobile 管理版。任何改動都應保持：

- 上游 EchoBot 的 MIT License 與 attribution。
- Web / Mobile 頁面結構清晰。
- 英文、繁體中文、簡體中文語言切換一致。
- 安全預設不暴露 secrets、不匿名公開高風險 API。
- Agent 工具權限預設保守。

### 開發流程

1. 從目前工作分支建立小範圍修改。
2. 避免把不相關重構和功能混在同一個 commit。
3. 新頁面或新 UI 文案要補三語 i18n。
4. 新第三方來源要補 `NOTICE.md` 或相鄰 attribution。
5. 新安全邊界、外部 provider、通訊平台或 Agent 工具要補測試。
6. 提交前至少跑最小可重現檢查。

### 開發環境

```shell
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
```

`requirements.txt` 是 runtime 安裝；開發、pytest 與瀏覽器 smoke 請使用 `requirements-dev.txt`。

### 必跑檢查

```shell
python -m pytest
```

前端改動至少檢查：

```shell
for f in $(find echobot/app/web -path '*/vendor/*' -prune -o -name '*.js' -print); do
  node --check "$f" || exit 1
done
```

### UI 規則

- `/stage` 是純展示，不放即時操作設定。
- `/messenger` 是通訊入口，預設 `chat_only`。
- `/console` 是操作員中台，放即時控制。
- `/admin` 與子頁是後台索引、設定、文件與整合說明。
- 手機 360/390/430px 不應有水平 overflow。

### Secrets 規則

不要提交：

- `.env`
- `.echobot/`
- API keys
- Cloudflare tokens
- Open WebUI bridge token
- Bot tokens / client secrets
- Session history / attachments

## English version

### Development Principles

This repository currently focuses on the EchoBot Web/Mobile management edition. Every change should preserve:

- Upstream EchoBot MIT License and attribution.
- Clear Web / Mobile page structure.
- Consistent English, Traditional Chinese, and Simplified Chinese language switching.
- Safe defaults that do not expose secrets or anonymous high-risk APIs.
- Conservative Agent tool permissions by default.

### Development Flow

1. Make small scoped changes from the current work branch.
2. Do not mix unrelated refactors with feature work in the same commit.
3. Add three-language i18n for new pages or UI copy.
4. Add attribution to `NOTICE.md` or the adjacent directory for new third-party sources.
5. Add tests for new security boundaries, external providers, channel integrations, or Agent tools.
6. Run at least the smallest rerunnable verification before committing.

### Development Environment

```shell
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
playwright install chromium
```

`requirements.txt` is the runtime install. Use `requirements-dev.txt` for development, pytest, and browser smoke checks.

### Required Checks

```shell
python -m pytest
```

For frontend changes, also run:

```shell
for f in $(find echobot/app/web -path '*/vendor/*' -prune -o -name '*.js' -print); do
  node --check "$f" || exit 1
done
```

### UI Rules

- `/stage` is display-only and should not contain live operator settings.
- `/messenger` is the chat entry and defaults to `chat_only`.
- `/console` is the operator workbench for live controls.
- `/admin` and its child pages are for admin indexes, settings, docs, and integration guidance.
- Mobile 360/390/430px viewports should not have horizontal overflow.

### Secrets Rules

Do not commit:

- `.env`
- `.echobot/`
- API keys
- Cloudflare tokens
- Open WebUI bridge token
- Bot tokens / client secrets
- Session history / attachments

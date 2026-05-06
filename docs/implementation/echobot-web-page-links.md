# EchoBot Web Page Links

## 中文版

本文件整理 EchoBot Web/Mobile 管理版目前可用的主要頁面。預設本機開發服務使用：

```text
http://127.0.0.1:8001
```

若你使用其他 port，將下面連結的 `8001` 換成實際 port。

| 分層 | 頁面 | 本機連結 | 用途 |
|---|---|---|---|
| 前台 | Stage | http://127.0.0.1:8001/stage?session_name=default | 正式顯示角色、字幕、TTS/Live2D 同步 |
| 通訊入口 | Messenger | http://127.0.0.1:8001/messenger?session_name=default | 內部 Web chat，以 Session 繼續對話 |
| 中台 | Console | http://127.0.0.1:8001/console | 測試、操作、Session/角色/模型/語音互動 |
| 相容入口 | Web Console | http://127.0.0.1:8001/web | 舊 `/web` 相容入口，指向 Console UI |
| 後台 | Admin Index | http://127.0.0.1:8001/admin | 後台索引與主要管理入口 |
| 後台 | Sessions | http://127.0.0.1:8001/admin/sessions | Session 建立、角色、route mode、channel binding |
| 後台 | Characters | http://127.0.0.1:8001/admin/characters | 角色 prompt、模型/語音/Live2D 綁定、emotion map、package 匯入匯出 |
| 後台 | LLM Models | http://127.0.0.1:8001/admin/models | LLM model profiles、provider/base URL/API key 設定 |
| 後台 | Voice Models | http://127.0.0.1:8001/admin/voice-models | STT/TTS profile 檢視與後續管理入口 |
| 後台 | Live2D | http://127.0.0.1:8001/admin/live2d | Live2D asset/config 檢視與後續管理入口 |
| 後台 | Channels | http://127.0.0.1:8001/admin/channels | Telegram/Discord 設定、secret redaction、smoke readiness |
| 後台 | Open WebUI Bridge | http://127.0.0.1:8001/admin/openwebui | Open WebUI 對接說明、bridge status、tool spec 入口 |
| 後台文件 | Operation Guide | http://127.0.0.1:8001/admin/guide | 操作、設定、預期結果、故障判斷與排除 |
| 後台文件 | Site Structure | http://127.0.0.1:8001/admin/structure | 頁面分層、資料流、架構邊界 |
| API 文件 | Swagger Docs | http://127.0.0.1:8001/docs | FastAPI Swagger UI |
| API 文件 | ReDoc | http://127.0.0.1:8001/redoc | FastAPI ReDoc |
| API 文件 | OpenAPI JSON | http://127.0.0.1:8001/openapi.json | 全站 OpenAPI schema |
| Bridge API | Open WebUI Tool Spec | `GET /api/openwebui/tools/openapi.json` | 給 Open WebUI 匯入的窄化 tool schema；需要 `Authorization: Bearer <ECHOBOT_OPENWEBUI_BRIDGE_TOKEN>`，不是一般瀏覽器直開頁面 |
| Health | API Health | http://127.0.0.1:8001/api/health | 本機服務健康檢查 |

主要操作順序建議：

1. 到 `/admin/models` 設定 LLM profile。
2. 到 `/admin/characters` 建立或調整角色。
3. 到 `/admin/sessions` 建立 Session，並選角色與 channel binding。
4. 用 `/console` 測試角色與模型回覆。
5. 用 `/stage?session_name=<session>` 開前台顯示。
6. 用 `/messenger?session_name=<session>` 或外部 channel 做正式互動。

Open WebUI bridge tool spec 驗證方式：

```bash
curl -H "Authorization: Bearer $ECHOBOT_OPENWEBUI_BRIDGE_TOKEN" \
  http://127.0.0.1:8001/api/openwebui/tools/openapi.json
```

## English version

This document lists the main pages currently available in the EchoBot Web/Mobile management edition. The default local development service is:

```text
http://127.0.0.1:8001
```

If you run on another port, replace `8001` in the links below with the actual port.

| Layer | Page | Local Link | Purpose |
|---|---|---|---|
| Front Stage | Stage | http://127.0.0.1:8001/stage?session_name=default | Production display for character, subtitles, TTS, and Live2D sync |
| Communication | Messenger | http://127.0.0.1:8001/messenger?session_name=default | Internal Web chat that continues an existing Session |
| Console | Console | http://127.0.0.1:8001/console | Testing and operation for Session, character, model, voice, and interaction flows |
| Compatibility | Web Console | http://127.0.0.1:8001/web | Legacy `/web` compatibility entry pointing to the Console UI |
| Admin | Admin Index | http://127.0.0.1:8001/admin | Admin index and main management entry |
| Admin | Sessions | http://127.0.0.1:8001/admin/sessions | Session creation, character, route mode, and channel binding |
| Admin | Characters | http://127.0.0.1:8001/admin/characters | Character prompts, model/voice/Live2D bindings, emotion maps, package import/export |
| Admin | LLM Models | http://127.0.0.1:8001/admin/models | LLM model profiles, provider/base URL/API key settings |
| Admin | Voice Models | http://127.0.0.1:8001/admin/voice-models | STT/TTS profile management, naming, provider settings, and smoke checks |
| Admin | Live2D | http://127.0.0.1:8001/admin/live2d | Live2D asset/profile management, naming, config, and stage binding |
| Admin | Channels | http://127.0.0.1:8001/admin/channels | Telegram/Discord settings, secret redaction, and smoke readiness |
| Admin | Open WebUI Bridge | http://127.0.0.1:8001/admin/openwebui | Open WebUI bridge guide, bridge status, and tool spec entry |
| Admin Docs | Operation Guide | http://127.0.0.1:8001/admin/guide | Operation, setup, expected results, failure signs, and troubleshooting |
| Admin Docs | Site Structure | http://127.0.0.1:8001/admin/structure | Page layering, data flow, and architecture boundaries |
| API Docs | Swagger Docs | http://127.0.0.1:8001/docs | FastAPI Swagger UI |
| API Docs | ReDoc | http://127.0.0.1:8001/redoc | FastAPI ReDoc |
| API Docs | OpenAPI JSON | http://127.0.0.1:8001/openapi.json | Full-site OpenAPI schema |
| Bridge API | Open WebUI Tool Spec | `GET /api/openwebui/tools/openapi.json` | Narrow tool schema for Open WebUI import; requires `Authorization: Bearer <ECHOBOT_OPENWEBUI_BRIDGE_TOKEN>` and is not a direct browser page |
| Health | API Health | http://127.0.0.1:8001/api/health | Local service health check |

Recommended operation order:

1. Configure the LLM profile in `/admin/models`.
2. Create or adjust a character in `/admin/characters`.
3. Create a Session in `/admin/sessions`, then select the character and channel binding.
4. Test the character and model response in `/console`.
5. Open the frontend display with `/stage?session_name=<session>`.
6. Use `/messenger?session_name=<session>` or an external channel for production interaction.

Open WebUI bridge tool spec verification:

```bash
curl -H "Authorization: Bearer $ECHOBOT_OPENWEBUI_BRIDGE_TOKEN" \
  http://127.0.0.1:8001/api/openwebui/tools/openapi.json
```

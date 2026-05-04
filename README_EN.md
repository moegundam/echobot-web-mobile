<div align="center">

<img src="./assets/banner.jpg" width="100%" alt="EchoBot Banner" />

</div>

# EchoBot Web Mobile Management Edition

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> Traditional Chinese version: [README.md](./README.md)

`moegundam/echobot-web-mobile` is a private management edition based on [KdaiP/EchoBot](https://github.com/KdaiP/EchoBot). Its goal is to extend the original EchoBot into a Web/Mobile version suitable for local development, mobile testing, 10-user private testing, Stage display, Messenger chat entry, Console operations, and Admin management.

EchoBot remains the implementation base. [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) is not merged into this backend. It is used only as a reference for Live2D, ASR/TTS, VTuber interaction design, and desktop-companion style UX.

## Sources And Attribution

| Type | Project | How this edition uses it |
|---|---|---|
| Upstream base | [KdaiP/EchoBot](https://github.com/KdaiP/EchoBot) | Main repository source for Agent/runtime/WebUI/Live2D/ASR/TTS/Channel foundations |
| Interaction reference | [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | Reference only for Live2D, voice interaction, and VTuber UX; its backend is not merged |
| Original license | MIT License | The original `LICENSE` is preserved; copyright belongs to KdaiP |

Any future third-party project, model, asset, or document reference must state its source, license, and purpose in the README, the relevant documentation, or the asset directory.

## What This Edition Adds To Original EchoBot

### 1. Layered Web Product Entrances

Original EchoBot mainly used `/web` as the operation page. This edition adds and organizes multiple product entrances:

| Page | Path | Purpose |
|---|---|---|
| Stage | `/stage?session_name=<name>` | Display-only character view, subtitles, TTS, and Live2D lip sync; can select a configured messaging target |
| Messenger | `/messenger` | Lightweight chat entry, defaulting to `chat_only`; can select configured Telegram/Discord targets instead of typing a session |
| Console | `/console` | Operator workbench, carrying the original `/web` control surface |
| Compatible Web | `/web` | Preserved legacy entry, mapped to Console |
| Admin | `/admin` | Admin index, health, API docs, jobs, and management pages |
| Operation Guide | `/admin/guide` | Operation, setup, expected outcomes, failure signs, and troubleshooting |
| Site Structure | `/admin/structure` | Route map, Console sections, and API namespace boundaries |
| Characters | `/admin/characters` | Manage role prompts, model profile binding, voice, Live2D summary, emotion maps, and character package import/export |
| Model Profiles | `/admin/models` | Create, rename, and activate role/model profiles |
| Channels | `/admin/channels` | Telegram / Discord setup and smoke checks, plus QQ/LINE/WhatsApp gateway management entry |
| Open WebUI Bridge | `/admin/openwebui` | Narrow OpenAPI bridge instructions for Open WebUI |

### 2. Mobile And Desktop Display Modes

This edition adds consistent language and display controls:

- Languages: English, Traditional Chinese, Simplified Chinese.
- Display modes: Auto, Mobile, Portrait, Landscape, Desktop / Dense.
- Console, Stage, Messenger, and Admin pages share the same switching pattern.
- `/console` adapts its operation layout based on device and selected display mode.

### 3. Sitewide Language Switching

The original static DOM translation approach has been expanded to dynamic modules:

- ASR, TTS, sessions, roles, Live2D, traces, attachments, and messages refresh when the language changes.
- Dynamic buttons, placeholders, titles, aria labels, status text, and error messages are no longer hard-coded inside feature modules.
- The default language is English, with Traditional Chinese and Simplified Chinese available.

### 4. Cloudflare Local Tunnel Testing Deployment

A Local Tunnel profile was added for private testing: EchoBot runs locally or on a Mac host, while Cloudflare Tunnel + Access provides HTTPS and login.

Related files:

- [`docs/deployment/local-tunnel.md`](./docs/deployment/local-tunnel.md)
- [`docs/deployment/cloudflared-local-tunnel.example.yml`](./docs/deployment/cloudflared-local-tunnel.example.yml)
- [`.env.local-tunnel.example`](./.env.local-tunnel.example)

Recommended Local Tunnel command:

```shell
python -m echobot app --host 127.0.0.1 --port 8000
```

For local development, use another port when needed:

```shell
python -m echobot app --host 127.0.0.1 --port 8001
```

### 5. Cloudflare Access Trusted-User Boundary

This edition adds trusted-header support so private-test data can be isolated by logged-in identity:

- Default trusted user header: `Cf-Access-Authenticated-User-Email`
- When enabled, protected pages, API docs, `/api/*`, and the ASR WebSocket require a trusted user id.
- Sessions, history, jobs, attachments, and settings are stored under `.echobot/users/<user_id>/...`.
- Different users should not see each other's sessions, history, jobs, attachments, or Stage events.
- `ECHOBOT_ADMIN_ALLOWLIST` can restrict high-risk mutation APIs for runtime, channels, roles, and model profiles.

### 6. Stage Event Broker

A user/session scoped Stage event flow was added:

- `GET /api/stage/events?session_name=<name>`: subscribe to Stage events over SSE.
- `POST /api/stage/events`: publish subtitles and stage events.
- Broker v1 is in-memory and keyed by trusted user plus session.
- Stage updates subtitles on `assistant_delta` and performs final subtitle/TTS behavior on `assistant_final`.
- Stage events can carry `emotion`, `expression`, and `motion`; `character_state` can update Live2D expression/motion without changing subtitles.
- `/admin/characters` can maintain an emotion map per character; when an event only provides `emotion` and the session has a bound role, the backend fills the mapped Live2D `expression` / `motion`.

### 7. Open WebUI Bridge Interface

The bridge interface is implemented, but Open WebUI does not need to be connected yet:

- `GET /api/openwebui/tools/openapi.json`
- `GET /api/openwebui/sessions`
- `POST /api/openwebui/stage/events`
- `POST /api/openwebui/chat`

Security design:

- The bridge uses a server-to-server Bearer token.
- The full site `/openapi.json` is not exposed to Open WebUI.
- By default, bridge calls require `target_user_id` or `ECHOBOT_OPENWEBUI_BRIDGE_USER_ID` so they do not write into the shared root runtime.
- `ECHOBOT_OPENWEBUI_ALLOWED_TARGET_USERS` can restrict which user namespaces the bridge may target.
- The default route mode is `chat_only`.
- Operator-agent mode must be explicitly enabled before higher-risk routing is allowed.

### 8. Model Profiles

A model profile management page was added:

- Default A-E profiles.
- Users can keep adding profiles.
- Profile names are user-defined.
- Each profile can configure chat, TTS, ASR, Live2D provider/model/base URL/API key values.
- Activating a profile updates the model settings used by Console.

### 9. Character Packages

`/admin/characters` can export and import one character package:

- Exports include the role prompt, model profile binding, emotion map, and a non-sensitive model settings snapshot.
- Exports do not include API keys, bot tokens, Cloudflare/Open WebUI tokens, or `.echobot/` secrets.
- Imports can use a new character name or overwrite an existing character.
- v1 uses JSON packages and does not bundle Live2D asset files; model API keys are still filled from `/admin/models`.

### 10. Channels Admin Page

`/admin/channels` has been upgraded from a read-only planning page into a messaging-platform setup entry:

- Telegram can store enabled state, allow list, bot token, proxy, and reply-to-message behavior.
- Discord can store enabled state, allow list, bot token, webhook URL, webhook secret, application/guild/channel ids.
- Secret fields only expose configured status in the API and UI; plaintext values are never returned.
- `POST /api/channels/{channel}/smoke` provides safe local readiness checks without echoing tokens in responses.
- `GET /api/channels/stage-targets` exposes a secret-free messaging target list so `/stage` and `/messenger` can select the Stage session bound to a configured platform.
- The Telegram polling runtime has passed a local bot E2E smoke; the test token is stored only in repo-external ignored runtime config and is not committed.
- Production messaging gateways can set `mirror_to_stage` and `stage_session_name`; Telegram replies have been verified to mirror into the `/stage` frontend.
- Discord is config/smoke-ready for now; its runtime adapter is still a later implementation slice.

### 11. Deployment And Architecture Documentation

This edition adds planning, site structure, and reference documents:

- [`docs/implementation/echobot-web-mobile-integration-plan.md`](./docs/implementation/echobot-web-mobile-integration-plan.md)
- [`docs/implementation/echobot-web-site-structure.md`](./docs/implementation/echobot-web-site-structure.md)
- [`docs/implementation/open-llm-vtuber-reference-gap.md`](./docs/implementation/open-llm-vtuber-reference-gap.md)

## Current Status And Public-Repo Notes

Completed so far:

- The EchoBot base has been organized into a Web/Mobile management edition while preserving the compatible `/web` entry.
- `/stage`, `/messenger`, `/console`, `/admin`, and the Admin guide/structure/models/Open WebUI/channels pages have been added.
- English, Traditional Chinese, and Simplified Chinese switching is applied to static pages and the main dynamic UI.
- Mobile/tablet/desktop display modes have been added, with 360x800, 390x844, 430x932, and 768x1024 viewport checks expected to avoid horizontal overflow.
- First-version interfaces and documentation exist for Cloudflare Local Tunnel, trusted-user isolation, Stage Event Broker, Open WebUI bridge APIs, Model Profiles, Character Packages, and Channels setup/smoke checks.
- The public-facing safety default is now `ECHOBOT_SHELL_SAFETY_MODE=workspace-write`.

Not finished or still planned:

- Telegram and QQ already have built-in runtime adapters. `/admin/channels` can now save Telegram / Discord settings and run smoke readiness checks, and Telegram local bot polling E2E plus Stage mirroring have passed. Discord, LINE, and WhatsApp production runtime adapters remain planned.
- The EchoBot-side narrow Open WebUI bridge API and documentation page exist, but Open WebUI does not need to be connected yet.
- `/admin` v1 is mostly an index, guide, and status surface. It is not a complete production SaaS admin console.
- Stage / Live2D / ASR / TTS have v1 integration and local smoke coverage. Real-device microphone and long-running voice interaction checks still need HTTPS plus real-device validation.
- Multi-user private testing should use Cloudflare Access or a trusted reverse proxy. Do not expose the local service anonymously to the public internet.

A public repository means the code and documentation are browseable. It does not mean this system is safe to deploy anonymously. Before internet deployment, read [`SECURITY.md`](./SECURITY.md) and enable the trusted-user security boundary.

## Quick Start

### 1. Install Dependencies

Python 3.11 or newer is recommended.

```shell
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create Configuration

```shell
cp .env.example .env
```

Common OpenAI-compatible configuration:

```text
LLM_API_KEY=your_api_key_here
LLM_MODEL=your-model-name
LLM_BASE_URL=https://your-provider.example/v1
```

Configure local models, remote private model services, and API keys in your own `.env` file or secret manager. Do not put real hosts, tailnet IPs, model inventories, or keys into a public repository.

### 3. Start The Local Server

```shell
python -m echobot app --host 127.0.0.1 --port 8000
```

If port 8000 is already in use:

```shell
python -m echobot app --host 127.0.0.1 --port 8001
```

### 4. Open The Pages

```text
http://127.0.0.1:8000/console
http://127.0.0.1:8000/stage?session_name=demo
http://127.0.0.1:8000/messenger
http://127.0.0.1:8000/admin
```

## Tests

```shell
python -m pytest
```

This branch has been verified with:

- 10 routes × mobile/desktop × 3 languages browser checks.
- i18n key coverage.
- API route/auth tests.
- Full pytest: `321 passed`.

## Project Rules

1. Preserve the upstream EchoBot MIT License and copyright.
2. Any third-party source used by README, docs, assets, models, or code must state its source, license, and purpose.
3. Secrets must not be committed, including LLM keys, Cloudflare tokens, Open WebUI bridge tokens, and chat platform bot tokens.
4. Private testing should use Cloudflare Access or a trusted reverse proxy first; do not expose the system anonymously by default.
5. `/messenger` and external chat gateways default to `chat_only`; tool-capable Agent behavior needs a separate approval gate.
6. User data is stored under `.echobot/users/<user_id>/...` by default and must not be mixed across users.
7. New pages must support English, Traditional Chinese, and Simplified Chinese.
8. Major features need documentation and tests, with at least one rerunnable minimum verification path.

## License

This project follows the upstream EchoBot MIT License. See [`LICENSE`](./LICENSE).

Original copyright:

```text
Copyright (c) 2026 KdaiP
```

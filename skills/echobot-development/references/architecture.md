# Architecture

Read this file when a change crosses module boundaries or when you need to trace a user turn end to end.

## Top-level entrypoints

- `echobot/cli/main.py` is the unified CLI. With no subcommand it falls back to chat mode.
- `echobot/cli/chat.py`, `echobot/cli/gateway.py`, and `echobot/cli/app.py` all build the shared runtime through `echobot/runtime/bootstrap.py`.
- `echobot/app/create_app.py` builds the FastAPI app, mounts routers, and serves the browser UI from `echobot/app/web/`.
- `echobot/app/runtime.py` wraps the shared runtime with channel, gateway, ASR, TTS, delivery, and web-console services.

## Shared runtime assembly

`build_runtime_context(...)` in `echobot/runtime/bootstrap.py` is the single assembly point. It creates:

- `AttachmentStore`
- provider instances for the main agent, decider, and roleplay layers
- `AgentCore`
- session stores for user sessions and agent sessions
- `AgentTraceStore`
- a `ToolRegistry` factory
- `SkillRegistry`
- `CronService` and optional `HeartbeatService`
- `SessionAgentRunner`
- `RoleCardRegistry`
- `DecisionEngine`
- `RoleplayEngine`
- `ConversationCoordinator`

If a feature should exist in chat, gateway, and app, wire it here once.

## User turn flow

1. A CLI command, gateway event, or API handler resolves a session and calls the coordinator.
2. `ConversationCoordinator.handle_user_turn_stream(...)` loads session state, role, and route mode.
3. Route mode decides how much routing logic to run: `chat_only` and `force_agent` short-circuit, while `auto` calls `DecisionEngine.decide(...)`.
4. Chat turns go to `RoleplayEngine.stream_chat_reply(...)`.
5. Agent turns can emit a delegated acknowledgement through the roleplay layer, then start background work.
6. `SessionAgentRunner.run_prompt(...)` calls `run_agent_turn(...)`.
7. `run_agent_turn(...)` prefers `ask_with_skills(...)`, then `ask_with_tools(...)`, then `ask_with_memory(...)`.
8. `AgentCore.ask_with_skills(...)` adds the skill catalog prompt, injects explicit `/skill-name` or `$skill-name` activations, and layers in `activate_skill`, `list_skill_resources`, and `read_skill_resource`.
9. Final agent output flows back through `RoleplayEngine.present_agent_result(...)`, `present_agent_failure(...)`, or scheduled-task presenters before it reaches CLI, gateway, or API clients.

## Base tools and skills

- `create_basic_tool_registry(...)` in `echobot/tools/builtin.py` builds the shared base tool set.
- The default tools are current time, directory listing, text file read or write, web requests, and shell commands.
- If attachments are enabled, media tools are added for viewing images and sending image or file outputs back to the user.
- If memory is enabled, the memory search tool is added.
- If cron is enabled, the cron tool is added. Scheduled runs keep the tool readable but disable mutations.
- Skill tools are not part of the base registry. They are layered in by `AgentCore.ask_with_skills(...)`.

## Layer boundaries

### Decision layer

- `echobot/orchestration/decision.py`
- `echobot/orchestration/route_modes.py`
- Use rules for obvious tool, workspace, memory, and scheduling requests.
- Use the lightweight decider LLM only for ambiguous turns.

### Roleplay layer

- `echobot/orchestration/roleplay.py`
- Use only visible conversation context plus role-card and system instructions.
- Do not inspect files, tools, schedules, or memory directly.

### Agent layer

- `echobot/agent.py`
- `echobot/runtime/session_runner.py`
- `echobot/runtime/turns.py`
- Own tool use, skill use, file access, shell calls, memory lookup, scheduling changes, and attachment-aware execution.

### Commands and control surfaces

- `echobot/commands/` handles `/route`, `/runtime`, `/role`, and saved-session command parsing and execution.
- `echobot/cli/session_commands.py` handles `/session ...` inside the interactive CLI chat loop.
- `echobot/app/routers/` exposes HTTP endpoints for chat, sessions, roles, cron, heartbeat, channels, attachments, and web-console assets.

### HTTP and application boundaries

- `echobot/app/create_app.py` is assembly only: middleware, routers, page routes, and static mounts.
- `echobot/app/routers/` owns HTTP dependencies, request/response contracts, and HTTP error mapping.
- `echobot/app/schemas.py` owns Pydantic contracts; `echobot/app/mappers.py` maps domain session/message objects into those contracts.
- `echobot/app/services/session_application.py` owns Session use cases.
- `echobot/app/services/character_profile_application.py` owns character mutations across role cards, profile settings, and live runtime bindings.
- `echobot/app/services/runtime_catalog_application.py` owns cross-store model deletion and Console runtime overrides.
- `echobot/app/services/deployment_status.py` owns read-only deployment probes and moves blocking Git/cloudflared/file checks off the event loop.
- `echobot/network/http.py` is the single shared HTTP URL and SSRF policy for providers, channels, speech, and web tools.
- Browser entrypoints use `echobot/app/web/modules/api.js` plus feature API modules; page files should not create duplicate JSON or NDJSON clients.

## Skills and role cards

- `SkillRegistry.discover(...)` searches project skills first, then local managed roots, then built-in skills.
- Project skills under `skills/` override built-in skills with the same `name`.
- Role cards are discovered from `echobot/roles/`, `roles/`, and `.echobot/roles/`.
- `.echobot/roles/default.md` is created automatically when missing.
- This repository can rely entirely on `roles/` or `.echobot/roles/`; `echobot/roles/` is an optional built-in root and may be absent.

## State files and managed directories

- Per-user runtime root: `.echobot/users/<user_storage_key>/`
- Sessions: `.echobot/users/<user_storage_key>/sessions/`
- Agent-side session history: `.echobot/users/<user_storage_key>/agent_sessions/`
- Agent traces: `.echobot/users/<user_storage_key>/agent_traces/`
- Runtime settings: `.echobot/runtime_settings.json`
- Cron store: `.echobot/cron/jobs.json`
- Heartbeat file: `.echobot/HEARTBEAT.md`
- Channel config: `.echobot/channels.json`
- Delivery state: `.echobot/delivery.json`
- Gateway route sessions: `.echobot/route_sessions.json`
- Attachments: `.echobot/attachments/`
- Managed roles: `.echobot/roles/`
- Live2D uploads: `.echobot/live2d/`
- Uploaded stage backgrounds: `.echobot/stage_backgrounds/`

## Current module map

- `echobot/skill_support/`: skill discovery, parsing, explicit activation, and lazy resource tools
- `echobot/tools/`: shared tool registry plus filesystem, shell, web, media, memory, and cron tools
- `echobot/runtime/`: bootstrap, sessions, traces, turn execution, and runtime settings
- `echobot/orchestration/`: coordinator, decision, roleplay, jobs, route modes, and role-card registry
- `echobot/commands/`: command parsing and execution for route mode, runtime settings, roles, and saved sessions
- `echobot/channels/`: channel configs, message bus, manager, registry, and platform adapters
- `echobot/gateway/`: route-session mapping, delivery state, and gateway runtime wiring
- `echobot/network/`: shared HTTP transport validation and private-network SSRF policy
- `echobot/app/services/`: application use cases, user/runtime scopes, catalog services, Stage broker, and deployment probes
- `echobot/app/mappers.py` and `echobot/app/schemas.py`: API mapping and transport contracts
- `echobot/app/services/web_console/`: Live2D, stage, and runtime-settings helpers for the browser UI
- `echobot/app/web/features/`: browser-side features grouped by chat, sessions, layout, Stage, Live2D, TTS, and ASR
- `echobot/attachments.py` and `echobot/images.py`: attachment persistence plus image limits and promotion
- `echobot/memory/`: ReMeLight integration
- `echobot/asr/` and `echobot/tts/`: speech services

## Test map

- `tests/test_skill_support.py`: skill discovery, activation, parsing, and lazy resource loading
- `tests/test_chat_agent.py`: CLI trace labels and async chat-loop behavior
- `tests/test_agent.py`, `tests/test_tools.py`, and `tests/test_agent_traces.py`: agent loop, tool execution, and trace persistence
- `tests/test_decision.py`, `tests/test_roleplay.py`, `tests/test_coordinator.py`, and `tests/test_roles.py`: routing, presentation, coordinator behavior, and role cards
- `tests/test_commands.py`, `tests/test_gateway.py`, and `tests/test_app_api.py`: command, gateway, and API surfaces
- `tests/test_sessions.py`, `tests/test_config.py`, and `tests/test_scheduler.py`: persisted runtime state and runtime configuration
- `tests/test_images.py`, `tests/test_channel_images.py`, and `tests/test_tts.py`: media-related flows

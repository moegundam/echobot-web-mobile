from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "echobot" / "app" / "web"


def test_non_speech_http_clients_use_generic_network_policy() -> None:
    module_paths = (
        ROOT / "echobot" / "providers" / "openai_compatible.py",
        ROOT / "echobot" / "channels" / "platforms" / "discord.py",
        ROOT / "echobot" / "channels" / "platforms" / "qq.py",
        ROOT / "echobot" / "tools" / "web.py",
    )

    for module_path in module_paths:
        source = module_path.read_text(encoding="utf-8")
        assert "speech_assets" not in source, module_path
        assert "network.http" in source, module_path


def test_admin_pages_share_the_json_api_client() -> None:
    app_paths = (
        WEB_ROOT / "models-app.js",
        WEB_ROOT / "voice-models-app.js",
        WEB_ROOT / "live2d-app.js",
        WEB_ROOT / "characters-app.js",
        WEB_ROOT / "sessions-app.js",
        WEB_ROOT / "channels-app.js",
    )

    for app_path in app_paths:
        source = app_path.read_text(encoding="utf-8")
        assert 'from "./modules/api.js"' in source, app_path
        assert "async function requestJson(" not in source, app_path


def test_deployment_router_delegates_blocking_probes_to_service() -> None:
    router_source = (
        ROOT / "echobot" / "app" / "routers" / "deployment.py"
    ).read_text(encoding="utf-8")

    assert "DeploymentStatusService" in router_source
    assert "subprocess" not in router_source
    assert "read_text(" not in router_source


def test_web_entrypoints_share_http_error_policy() -> None:
    app_paths = (
        WEB_ROOT / "admin-app.js",
        WEB_ROOT / "deployment-app.js",
        WEB_ROOT / "openwebui-app.js",
        WEB_ROOT / "session-runtime-context.js",
        WEB_ROOT / "messenger-app.js",
    )

    for app_path in app_paths:
        source = app_path.read_text(encoding="utf-8")
        assert 'from "./modules/api.js"' in source, app_path
        assert "async function responseToError(" not in source, app_path

    stage_api = (WEB_ROOT / "features" / "stage" / "api.js").read_text(
        encoding="utf-8"
    )
    assert 'from "../../modules/api.js"' in stage_api
    assert "async function responseToError(" not in stage_api


def test_runtime_model_services_return_plain_application_payloads() -> None:
    service_paths = (
        ROOT / "echobot" / "app" / "services" / "llm_models.py",
        ROOT / "echobot" / "app" / "services" / "voice_models.py",
        ROOT / "echobot" / "app" / "services" / "live2d_models.py",
    )

    for service_path in service_paths:
        source = service_path.read_text(encoding="utf-8")
        assert ".model_dump(" not in source, service_path
        assert "API projection" not in source, service_path


def test_schema_module_contains_contracts_not_domain_mapping_or_redaction() -> None:
    schema_source = (
        ROOT / "echobot" / "app" / "schemas.py"
    ).read_text(encoding="utf-8")

    assert "from ..models" not in schema_source
    assert "from ..runtime.sessions" not in schema_source
    assert "def session_detail_model_from_session" not in schema_source
    assert "CHANNEL_SECRET_FIELD_NAMES" not in schema_source


def test_messenger_reuses_shared_json_upload_and_stream_transports() -> None:
    messenger_source = (WEB_ROOT / "messenger-app.js").read_text(encoding="utf-8")

    assert "requestChatStream" in messenger_source
    assert "uploadChatImage" in messenger_source
    assert "uploadChatFile" in messenger_source
    assert "async function consumeNdjson(" not in messenger_source
    assert 'fetch("/api/chat/stream"' not in messenger_source


def test_character_router_delegates_mutations_to_application_service() -> None:
    router_source = (
        ROOT / "echobot" / "app" / "routers" / "character_profiles.py"
    ).read_text(encoding="utf-8")

    assert "CharacterProfileApplicationService" in router_source
    assert ".role_service.create_role(" not in router_source
    assert ".role_service.rename_role(" not in router_source
    assert ".role_service.delete_role(" not in router_source


def test_runtime_catalog_router_delegates_cross_store_mutations() -> None:
    router_source = (
        ROOT / "echobot" / "app" / "routers" / "session_catalog.py"
    ).read_text(encoding="utf-8")

    assert "RuntimeCatalogApplicationService" in router_source
    assert "clear_runtime_bindings_for_profile" not in router_source
    assert "clear_profile_references" not in router_source
    assert "session_runtime_override_service.set_override" not in router_source


def test_stage_entrypoint_delegates_echobot_http_transport() -> None:
    stage_source = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")
    stage_api = (WEB_ROOT / "features" / "stage" / "api.js").read_text(
        encoding="utf-8"
    )

    assert "createStageRuntimeController" in stage_source
    assert "createStageSpeechController" in stage_source
    assert 'fetch("/api/channels/stage-targets"' not in stage_source
    assert 'fetch("/api/web/tts"' not in stage_source
    assert 'fetch("/api/web/config"' not in stage_source
    assert 'from "../../modules/api.js"' in stage_api

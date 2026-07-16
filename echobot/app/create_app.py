from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import load_env_file
from ..runtime.bootstrap import RuntimeOptions
from .auth import (
    TRUSTED_USER_STATE_KEY,
    AdminAccessConfig,
    DeploymentSecurityConfig,
    TrustedUserConfig,
    is_protected_path,
    resolve_trusted_user_id,
    validate_deployment_security,
)
from .routers import (
    attachments,
    chat,
    character_profiles,
    channels,
    cron,
    deployment,
    health,
    heartbeat,
    model_profiles,
    openwebui,
    roles,
    session_catalog,
    sessions,
    stage,
    web,
)
from .runtime import ASRServiceBuilder, AppRuntime, RuntimeContextBuilder, TTSServiceBuilder
from .web_pages import WEB_PAGE_ROUTES


WEB_ASSETS_DIR = Path(__file__).with_name("web")


def create_app(
    *,
    runtime_options: RuntimeOptions | None = None,
    channel_config_path: str | Path = ".echobot/channels.json",
    context_builder: RuntimeContextBuilder | None = None,
    tts_service_builder: TTSServiceBuilder | None = None,
    asr_service_builder: ASRServiceBuilder | None = None,
) -> FastAPI:
    options = replace(
        runtime_options or RuntimeOptions(),
        allow_unconfigured_llm=True,
    )
    _load_runtime_env(options)
    runtime = AppRuntime(
        runtime_options=options,
        channel_config_path=channel_config_path,
        context_builder=context_builder,
        tts_service_builder=tts_service_builder,
        asr_service_builder=asr_service_builder,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await runtime.start()
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(
        title="EchoBot API",
        description="Runtime API for EchoBot daemon and future web console.",
        lifespan=lifespan,
    )
    deployment_security_config = DeploymentSecurityConfig.from_env()
    trusted_user_config = TrustedUserConfig.from_env()
    admin_access_config = AdminAccessConfig.from_env()
    validate_deployment_security(
        deployment_security_config,
        trusted_user_config,
        admin_access_config,
    )
    app.state.deployment_security_config = deployment_security_config
    app.state.trusted_user_config = trusted_user_config
    app.state.admin_access_config = admin_access_config

    @app.middleware("http")
    async def trusted_user_middleware(request, call_next):
        if trusted_user_config.enabled and is_protected_path(request.url.path):
            try:
                user_id = resolve_trusted_user_id(request.headers, trusted_user_config)
            except ValueError as error:
                return JSONResponse(
                    {"detail": str(error)},
                    status_code=401,
                )
            if not user_id and trusted_user_config.required:
                return JSONResponse(
                    {"detail": "Trusted user header is required"},
                    status_code=401,
                )
            if user_id:
                setattr(request.state, TRUSTED_USER_STATE_KEY, user_id)
        return await call_next(request)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "EchoBot API",
            "docs": "/docs",
        }

    @app.get("/healthz", include_in_schema=False)
    async def readiness():
        try:
            return await runtime.readiness_snapshot()
        except Exception:
            return JSONResponse(
                {"status": "unavailable"},
                status_code=503,
            )

    _register_web_page_routes(app)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(
            WEB_ASSETS_DIR / "favicon.svg",
            media_type="image/svg+xml",
        )

    app.mount(
        "/web/assets",
        StaticFiles(directory=WEB_ASSETS_DIR),
        name="web-assets",
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(attachments.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(character_profiles.router, prefix="/api")
    app.include_router(cron.router, prefix="/api")
    app.include_router(heartbeat.router, prefix="/api")
    app.include_router(roles.router, prefix="/api")
    app.include_router(model_profiles.router, prefix="/api")
    app.include_router(session_catalog.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(deployment.router, prefix="/api")
    app.include_router(stage.router, prefix="/api")
    app.include_router(openwebui.router, prefix="/api")
    app.include_router(web.router, prefix="/api")
    return app


def _load_runtime_env(options: RuntimeOptions) -> None:
    env_file_path = Path(options.env_file).expanduser()
    if not env_file_path.is_absolute():
        workspace = (options.workspace or Path(".")).resolve()
        env_file_path = workspace / env_file_path
    load_env_file(env_file_path)


def _register_web_page_routes(app: FastAPI) -> None:
    for route in WEB_PAGE_ROUTES:
        app.add_api_route(
            route.path,
            _web_page_handler(route.asset_name),
            methods=["GET"],
            include_in_schema=False,
            name=route.route_name,
        )


def _web_page_handler(asset_name: str):
    async def handler() -> FileResponse:
        return FileResponse(WEB_ASSETS_DIR / asset_name)

    return handler

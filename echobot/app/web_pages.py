from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebPageRoute:
    path: str
    asset_name: str
    route_name: str


WEB_PAGE_ROUTES: tuple[WebPageRoute, ...] = (
    WebPageRoute("/web", "index.html", "web_console"),
    WebPageRoute("/console", "index.html", "console"),
    WebPageRoute("/stage", "stage.html", "stage_page"),
    WebPageRoute("/messenger", "messenger.html", "messenger"),
    WebPageRoute("/admin", "admin.html", "admin"),
    WebPageRoute("/admin/guide", "guide.html", "admin_guide"),
    WebPageRoute("/admin/structure", "structure.html", "admin_structure"),
    WebPageRoute("/admin/deployment", "deployment.html", "admin_deployment"),
    WebPageRoute("/admin/sessions", "sessions.html", "admin_sessions"),
    WebPageRoute("/admin/channels", "channels.html", "admin_channels"),
    WebPageRoute("/admin/characters", "characters.html", "admin_characters"),
    WebPageRoute("/admin/openwebui", "openwebui.html", "admin_openwebui"),
    WebPageRoute("/admin/models", "models.html", "admin_models"),
    WebPageRoute("/admin/voice-models", "voice-models.html", "admin_voice_models"),
    WebPageRoute("/admin/live2d", "live2d.html", "admin_live2d"),
)

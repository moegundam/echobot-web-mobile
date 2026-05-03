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
    WebPageRoute("/admin/channels", "channels.html", "admin_channels"),
    WebPageRoute("/admin/openwebui", "openwebui.html", "admin_openwebui"),
    WebPageRoute("/admin/models", "models.html", "admin_models"),
)

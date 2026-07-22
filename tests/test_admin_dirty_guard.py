from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "echobot" / "app" / "web"

EDITOR_FILES = (
    "models-app.js",
    "voice-models-app.js",
    "live2d-app.js",
    "characters-app.js",
)


def test_dirty_guard_has_form_and_beforeunload_protection() -> None:
    source = (WEB_ROOT / "modules" / "dirty-form-guard.js").read_text(encoding="utf-8")

    assert "export function createDirtyFormGuard" in source
    assert 'element.addEventListener("input"' in source
    assert 'element.addEventListener("change"' in source
    assert "elements" in source
    assert 'window.addEventListener("beforeunload"' in source
    assert "event.returnValue" in source
    assert "confirmDiscard" in source


def test_all_admin_editors_wire_the_shared_dirty_guard() -> None:
    for filename in EDITOR_FILES:
        source = (WEB_ROOT / filename).read_text(encoding="utf-8")

        assert 'from "./modules/dirty-form-guard.js"' in source, filename
        assert "createDirtyFormGuard" in source, filename
        assert "const dirtyGuard = createDirtyFormGuard" in source, filename
        assert "form: DOM.form" in source, filename
        assert "dirtyGuard.confirmDiscard()" in source, filename
        assert "dirtyGuard.clear()" in source, filename
        if filename == "characters-app.js":
            assert "elements: [DOM.packageJson, DOM.packageImportName, DOM.packageOverwrite]" in source

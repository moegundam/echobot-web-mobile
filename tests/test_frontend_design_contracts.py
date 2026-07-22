from __future__ import annotations

from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "echobot" / "app" / "web"
LOCALE_FILES = (
    WEB_ROOT / "i18n" / "catalog-en.js",
    WEB_ROOT / "i18n" / "catalog-zh-Hant.js",
    WEB_ROOT / "i18n" / "catalog-zh-Hans.js",
)


def read_web_file(relative_path: str) -> str:
    return (WEB_ROOT / relative_path).read_text(encoding="utf-8")


def test_console_labels_local_runtime_overrides_and_stage_application_in_all_locales() -> None:
    console_html = read_web_file("index.html")
    locale_sources = [path.read_text(encoding="utf-8") for path in LOCALE_FILES]

    required_keys = (
        "console.runtimeLocalOverride",
        "console.runtimeAppliedToStage",
    )
    for key in required_keys:
        assert f'data-i18n-key="{key}"' in console_html
        assert all(f'"{key}"' in source for source in locale_sources)


def test_tablet_portrait_uses_workspace_tabs_instead_of_a_long_stacked_console() -> None:
    responsive_css = read_web_file("styles/responsive.css")
    workspace_js = read_web_file("features/layout/mobile-workspace.js")
    console_html = read_web_file("index.html")

    portrait_selector = 'html[data-layout-mode="tablet"]:not([data-viewport-orientation="landscape"])'
    assert portrait_selector in responsive_css
    assert 'data-console-workspace-tab="operations"' in console_html
    assert 'data-console-workspace-tab="chat"' in console_html
    assert 'data-layout-mode === "tablet"' in workspace_js
    assert 'data-viewport-orientation !== "landscape"' in workspace_js
    assert 'data-mobile-workspace-view="operations"' in responsive_css
    assert 'data-mobile-workspace-view="chat"' in responsive_css


def test_stage_exposes_fullscreen_and_auto_hide_capable_controls() -> None:
    stage_html = read_web_file("stage.html")
    stage_app = read_web_file("stage-app.js")
    stage_menu = read_web_file("features/stage/menu.js")
    stage_css = read_web_file("styles/shell-pages.css")

    assert 'id="stage-fullscreen-toggle"' in stage_html
    assert 'data-i18n-key="stage.fullscreen"' in stage_html
    assert 'data-i18n-key="stage.controlsAutoHide"' in stage_html
    assert "requestFullscreen" in stage_app or "requestFullscreen" in stage_menu
    assert "stageControlsAutoHide" in stage_app or "stageControlsAutoHide" in stage_menu
    assert ".stage-controls-auto-hidden" in stage_css


def test_console_model_and_voice_selectors_have_searchable_controls() -> None:
    console_html = read_web_file("index.html")
    console_app = read_web_file("app.js")
    tts_options = read_web_file("features/tts/options.js")

    assert 'id="model-profile-search"' in console_html
    assert 'id="voice-search"' in console_html
    assert 'type="search"' in console_html
    assert 'aria-controls="model-profile-select"' in console_html
    assert 'aria-controls="voice-select"' in console_html
    assert "model-profile-search" in console_app
    assert "voice-search" in tts_options
    assert "addEventListener(\"input\"" in console_app
    assert "addEventListener(\"input\"" in tts_options


def test_runtime_edit_module_is_a_local_state_boundary_without_admin_persistence_calls() -> None:
    runtime_edits = read_web_file("features/runtime-edits.js")

    assert "createRuntimeEditsController" in runtime_edits
    assert "markRuntimeDirty" in runtime_edits
    assert "markApplied" in runtime_edits
    assert "/api/" not in runtime_edits
    assert "requestJson" not in runtime_edits
    assert "fetch(" not in runtime_edits

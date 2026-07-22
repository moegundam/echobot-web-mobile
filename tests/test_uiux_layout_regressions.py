from __future__ import annotations

import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "echobot" / "app" / "web"


def css_rule_block(source: str, selector: str) -> str:
    start = source.index(f"{selector} {{")
    body_start = start + len(f"{selector} {{")
    end = source.index("\n}", body_start)
    return source[body_start:end]


class UiUxLayoutRegressionTests(unittest.TestCase):
    def test_stage_is_bounded_to_the_visual_viewport(self) -> None:
        shell_pages_css = (WEB_ROOT / "styles" / "shell-pages.css").read_text(
            encoding="utf-8",
        )

        stage_page = css_rule_block(shell_pages_css, ".stage-page")
        stage_surface = css_rule_block(shell_pages_css, ".stage-surface")
        stage_canvas = css_rule_block(shell_pages_css, ".stage-canvas-host canvas")
        stage_subtitle = css_rule_block(shell_pages_css, ".stage-subtitle-panel")

        self.assertIn("height: 100dvh", stage_page)
        self.assertIn("overflow: hidden", stage_page)
        self.assertIn("grid-template-rows: minmax(0, 1fr) auto", stage_surface)
        self.assertIn("height: 100%", stage_surface)
        self.assertIn("position: absolute", stage_canvas)
        self.assertIn("inset: 0", stage_canvas)
        self.assertIn("max-height: min(32dvh, 240px)", stage_subtitle)
        self.assertIn("overflow-y: auto", stage_subtitle)

    def test_stage_touch_controls_and_reduced_motion_are_accessible(self) -> None:
        shell_pages_css = (WEB_ROOT / "styles" / "shell-pages.css").read_text(
            encoding="utf-8",
        )

        audio_button = css_rule_block(shell_pages_css, ".stage-audio-button")
        reduced_motion = shell_pages_css.split(
            "@media (prefers-reduced-motion: reduce) {",
            1,
        )[1].split("\n}", 1)[0]

        self.assertIn("min-height: 44px", audio_button)
        self.assertIn(".stage-menu-panel", reduced_motion)
        self.assertIn("transition: none", reduced_motion)

    def test_console_reframes_live2d_model_when_stage_size_changes(self) -> None:
        scene_js = (WEB_ROOT / "features" / "live2d" / "scene.js").read_text(
            encoding="utf-8",
        )
        model_js = (WEB_ROOT / "features" / "live2d" / "model.js").read_text(
            encoding="utf-8",
        )
        live2d_index_js = (WEB_ROOT / "features" / "live2d" / "index.js").read_text(
            encoding="utf-8",
        )

        self.assertIn("const previousStageSize = currentStageSize();", scene_js)
        self.assertIn("reframeLive2DViewForResize(previousStageSize);", scene_js)
        self.assertIn("function reframeLive2DViewForResize(previousStageSize)", model_js)
        self.assertIn("model.x / previousWidth", model_js)
        self.assertIn("model.y / previousHeight", model_js)
        self.assertIn("reframeLive2DViewForResize", live2d_index_js)

    def test_stacked_console_layout_removes_settings_panel_nested_scroll(self) -> None:
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(
            encoding="utf-8",
        )

        self.assertIn(
            'html[data-layout-mode="mobile"] .settings-panel[open]',
            responsive_css,
        )
        self.assertIn("max-height: none", responsive_css)
        self.assertIn("overflow: hidden", responsive_css)

    def test_mobile_console_header_does_not_treat_desktop_flex_basis_as_height(self) -> None:
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(
            encoding="utf-8",
        )

        self.assertIn(
            'html[data-layout-mode="mobile"] .stage-header-meta',
            responsive_css,
        )
        self.assertIn("flex: 0 0 auto", responsive_css)
        self.assertIn(
            'html[data-layout-mode="mobile"] .console-quick-nav',
            responsive_css,
        )
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr))", responsive_css)
        self.assertIn(
            'html[data-layout-mode="mobile"] .console-language-switcher .shell-language-select-label',
            responsive_css,
        )
        self.assertIn("grid-template-columns: minmax(0, 1fr)", responsive_css)

    def test_admin_subpages_share_collapsible_current_page_navigation(self) -> None:
        navigation_js = (WEB_ROOT / "shell-admin-navigation.js").read_text(
            encoding="utf-8",
        )
        self.assertIn('link.setAttribute("aria-current", "page")', navigation_js)
        self.assertIn('className = "admin-nav-disclosure"', navigation_js)
        self.assertIn("data-i18n-key", navigation_js)

        pages = (
            "channels.html",
            "characters.html",
            "deployment.html",
            "guide.html",
            "live2d.html",
            "models.html",
            "openwebui.html",
            "sessions.html",
            "structure.html",
            "voice-models.html",
        )
        for page_name in pages:
            with self.subTest(page=page_name):
                html = (WEB_ROOT / page_name).read_text(encoding="utf-8")
                self.assertIn("/web/assets/shell-admin-navigation.js", html)

    def test_admin_health_summary_is_actionable_and_not_raw_json(self) -> None:
        html = (WEB_ROOT / "admin.html").read_text(encoding="utf-8")
        app_js = (WEB_ROOT / "admin-app.js").read_text(encoding="utf-8")

        self.assertIn('id="admin-health-refresh"', html)
        self.assertIn('id="admin-health-updated"', html)
        self.assertIn('id="admin-health-status"', html)
        self.assertIn('id="admin-health-session"', html)
        self.assertIn('id="admin-health-role"', html)
        self.assertIn('id="admin-health-channels"', html)
        self.assertIn('id="admin-health-jobs"', html)
        self.assertNotIn('<pre id="admin-health-output"', html)
        self.assertIn("renderHealthSnapshot", app_js)
        self.assertNotIn("JSON.stringify(safeHealthSnapshot", app_js)

    def test_mobile_profile_picker_is_horizontal_and_save_is_primary(self) -> None:
        shell_pages_css = (WEB_ROOT / "styles" / "shell-pages.css").read_text(
            encoding="utf-8",
        )
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(
            encoding="utf-8",
        )

        self.assertIn(".model-profile-save", shell_pages_css)
        self.assertIn(".model-profile-delete", shell_pages_css)
        self.assertIn(
            'html[data-layout-mode="mobile"] .model-profile-list',
            responsive_css,
        )
        self.assertIn("overflow-x: auto", responsive_css)

    def test_mobile_messenger_keeps_primary_chat_controls_in_early_view(self) -> None:
        shell_pages_css = (WEB_ROOT / "styles" / "shell-pages.css").read_text(
            encoding="utf-8",
        )

        self.assertIn(".messenger-header > div:first-child", shell_pages_css)
        self.assertIn(".messenger-header .display-mode-switcher", shell_pages_css)
        self.assertIn(".messenger-empty-state", shell_pages_css)
        self.assertIn("margin: 32px 12px", shell_pages_css)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "echobot" / "app" / "web"


class ConsoleMobileWorkspaceStaticTests(unittest.TestCase):
    def test_mobile_workspace_uses_existing_console_regions(self) -> None:
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        dom_js = (WEB_ROOT / "core" / "dom.js").read_text(encoding="utf-8")
        store_js = (WEB_ROOT / "core" / "store.js").read_text(encoding="utf-8")

        self.assertIn('id="console-mobile-workspace-tabs"', html)
        self.assertIn('role="tablist"', html)
        for view, label_key in (
            ("stage", "console.openStage"),
            ("operations", "console.controlPanel"),
            ("chat", "console.conversation"),
        ):
            self.assertIn(f'data-console-workspace-tab="{view}"', html)
            self.assertIn(f'data-i18n-key="{label_key}"', html)

        self.assertIn('data-console-workspace-region="stage"', html)
        self.assertIn('data-console-workspace-region="operations"', html)
        self.assertIn('data-console-workspace-region="chat"', html)
        self.assertIn("consoleMobileWorkspaceTabs", dom_js)
        self.assertIn('mobileWorkspaceView: "stage"', store_js)

    def test_mobile_workspace_controller_handles_layout_and_keyboard(self) -> None:
        app_js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        controller_js = (
            WEB_ROOT / "features" / "layout" / "mobile-workspace.js"
        ).read_text(encoding="utf-8")

        self.assertIn("initMobileConsoleWorkspace", app_js)
        self.assertIn("usesTabbedWorkspace", controller_js)
        self.assertIn('layoutMode === "mobile"', controller_js)
        self.assertIn('layoutMode === "tablet"', controller_js)
        self.assertIn('viewportOrientation !== "landscape"', controller_js)
        self.assertIn(
            'attributeFilter: ["data-layout-mode", "data-viewport-orientation"]',
            controller_js,
        )
        self.assertIn('setAttribute("aria-selected"', controller_js)
        self.assertIn('setAttribute("aria-hidden"', controller_js)
        self.assertIn("ArrowLeft", controller_js)
        self.assertIn("ArrowRight", controller_js)
        self.assertIn("Home", controller_js)
        self.assertIn("End", controller_js)
        self.assertNotIn("cloneNode", controller_js)
        self.assertNotIn("localStorage", controller_js)

    def test_mobile_workspace_closes_drawers_before_hiding_their_region(self) -> None:
        app_js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        controller_js = (
            WEB_ROOT / "features" / "layout" / "mobile-workspace.js"
        ).read_text(encoding="utf-8")

        self.assertIn("onViewChange = () => {}", controller_js)
        self.assertIn("onViewChange(view);", controller_js)
        self.assertIn("function handleMobileWorkspaceViewChange(view)", app_js)
        self.assertIn(
            "layout.setLive2DDrawerOpen(false, { restoreFocus: false });",
            app_js,
        )
        self.assertIn(
            "layout.setSessionSidebarOpen(false, { restoreFocus: false });",
            app_js,
        )
        self.assertIn(
            "layout.setRoleSidebarOpen(false, { restoreFocus: false });",
            app_js,
        )

    def test_mobile_workspace_css_does_not_change_tablet_or_desktop_split(self) -> None:
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(
            encoding="utf-8",
        )

        self.assertIn(".console-mobile-workspace-tabs {", responsive_css)
        self.assertIn("display: none", responsive_css)
        self.assertIn(
            'html[data-layout-mode="mobile"] .console-mobile-workspace-tabs',
            responsive_css,
        )
        self.assertIn(
            '[data-mobile-workspace-view="stage"] .chat-panel',
            responsive_css,
        )
        self.assertIn(
            '[data-mobile-workspace-view="operations"] .stage-panel',
            responsive_css,
        )
        self.assertIn(
            '[data-mobile-workspace-view="operations"] .conversation-panel',
            responsive_css,
        )
        self.assertIn(
            '[data-mobile-workspace-view="chat"] .stage-panel',
            responsive_css,
        )
        self.assertIn(
            '[data-mobile-workspace-view="chat"] .console-operations-workspace',
            responsive_css,
        )
        self.assertNotIn(
            'html[data-layout-mode="tablet"] .console-mobile-workspace-tabs',
            responsive_css,
        )
        self.assertNotIn(
            'html[data-layout-mode="desktop"] .console-mobile-workspace-tabs',
            responsive_css,
        )

    def test_mobile_workspace_is_bounded_to_the_dynamic_viewport(self) -> None:
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(
            encoding="utf-8",
        )

        self.assertIn(
            'html[data-layout-mode="mobile"] body {\n    overflow: hidden;',
            responsive_css,
        )
        self.assertIn(
            'html[data-layout-mode="mobile"] .page-shell {\n'
            '    grid-template-columns: 1fr;\n'
            '    grid-template-rows: auto minmax(0, 1fr);',
            responsive_css,
        )
        self.assertIn("height: 100dvh;", responsive_css)
        self.assertIn(
            'html[data-layout-mode="mobile"] .live2d-stage {\n'
            '    min-height: 0;',
            responsive_css,
        )
        self.assertIn(
            '[data-mobile-workspace-view="operations"] .chat-main {\n'
            '    overflow: auto;',
            responsive_css,
        )

    def test_console_core_modules_share_one_import_map_identity(self) -> None:
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        versioned_direct_imports: list[str] = []
        for path in WEB_ROOT.rglob("*.js"):
            source = path.read_text(encoding="utf-8")
            for module_name in ("dom", "store"):
                if f"core/{module_name}.js?" in source:
                    versioned_direct_imports.append(str(path.relative_to(WEB_ROOT)))

        self.assertIn('<script type="importmap">', html)
        import_map_match = re.search(
            r'<script type="importmap">\s*(.*?)\s*</script>',
            html,
            re.DOTALL,
        )
        self.assertIsNotNone(import_map_match)
        imports = json.loads(import_map_match.group(1))["imports"]
        for module_name in ("dom", "store"):
            canonical_name = f"/web/assets/core/{module_name}.js"
            canonical_target = imports[canonical_name]
            self.assertTrue(canonical_target.startswith(f"{canonical_name}?v="))
            self.assertEqual(
                canonical_target,
                imports[f"{canonical_name}?v=uiux-1"],
            )
        self.assertEqual([], versioned_direct_imports)

    def test_responsive_stylesheet_import_is_versioned_with_current_uiux(self) -> None:
        index_css = (WEB_ROOT / "styles" / "index.css").read_text(encoding="utf-8")
        self.assertIn('responsive.css?v=display-menu-1&uiux=4', index_css)


if __name__ == "__main__":
    unittest.main()

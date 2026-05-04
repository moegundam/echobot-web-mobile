from __future__ import annotations

import re
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1] / "echobot" / "app" / "web"


class WebStaticAssetTests(unittest.TestCase):
    def test_display_mode_uses_layout_mode_contract(self) -> None:
        display_mode_js = (WEB_ROOT / "shell-display-mode.js").read_text(encoding="utf-8")
        responsive_css = (WEB_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        shell_pages_css = (WEB_ROOT / "styles" / "shell-pages.css").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn("dataset.layoutMode", display_mode_js)
        self.assertIn("dataset.requestedDisplayMode", display_mode_js)
        self.assertIn('"displayMode.tablet"', i18n_js)
        self.assertNotIn('{ code: "portrait"', display_mode_js)
        self.assertNotIn('{ code: "landscape"', display_mode_js)
        self.assertNotIn('data-effective-display-mode="portrait"', responsive_css)
        self.assertNotIn('data-effective-display-mode="landscape"', responsive_css)
        self.assertNotIn('data-effective-display-mode="portrait"', shell_pages_css)
        self.assertNotIn('data-effective-display-mode="landscape"', shell_pages_css)

    def test_html_translatable_attributes_have_i18n_keys(self) -> None:
        checked_attributes = {
            "aria-label": "data-i18n-aria-label-key",
            "placeholder": "data-i18n-placeholder-key",
            "title": "data-i18n-title-key",
        }

        failures: list[str] = []
        for html_path in sorted(WEB_ROOT.glob("*.html")):
            html = html_path.read_text(encoding="utf-8")
            for match in re.finditer(r"<([A-Za-z][\w:-]*)([^<>]*)>", html):
                tag_name = match.group(1).lower()
                if tag_name in {"html", "meta", "link", "script"}:
                    continue
                attrs = match.group(2)
                for attr_name, i18n_attr_name in checked_attributes.items():
                    if re.search(rf"\b{re.escape(attr_name)}=\"[^\"]+\"", attrs):
                        if not re.search(rf"\b{re.escape(i18n_attr_name)}=\"[^\"]+\"", attrs):
                            failures.append(
                                f"{html_path.relative_to(WEB_ROOT)} <{tag_name}> missing {i18n_attr_name} for {attr_name}",
                            )

        self.assertEqual([], failures)

    def test_console_exposes_role_model_profile_and_control_groups(self) -> None:
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
        roles_js = (WEB_ROOT / "features" / "roles.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('id="role-model-profile-card"', html)
        self.assertIn('id="role-model-profile-link"', html)
        self.assertIn('id="role-model-profile-detail"', html)
        self.assertIn('data-i18n-key="console.groupModelRouting"', html)
        self.assertIn('data-i18n-key="console.groupVoice"', html)
        self.assertIn('data-i18n-key="console.groupLive2dStage"', html)
        self.assertIn('data-i18n-key="console.groupRuntimeJobs"', html)
        self.assertIn("syncModelProfileFromServer", app_js)
        self.assertIn("renderRoleModelProfileCard", roles_js)

        for key in (
            "console.roleModelProfile",
            "console.roleModelProfileBound",
            "console.roleModelProfileUnbound",
            "console.roleSwitchedWithProfile",
            "console.groupModelRouting",
            "console.groupVoice",
            "console.groupLive2dStage",
            "console.groupRuntimeJobs",
        ):
            self.assertIn(f'"{key}"', i18n_js)

    def test_messenger_stage_stream_contract_is_explicit(self) -> None:
        messenger_js = (WEB_ROOT / "messenger-app.js").read_text(encoding="utf-8")
        stage_js = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")

        self.assertIn('route_mode: DEFAULT_ROUTE_MODE', messenger_js)
        self.assertIn('const DEFAULT_ROUTE_MODE = "chat_only";', messenger_js)
        self.assertIn("extractStageDirectives", messenger_js)
        self.assertIn("stageDirectivePattern", messenger_js)
        self.assertIn('await publishStageEvent("subtitle", sessionName, ""', messenger_js)
        self.assertIn('await publishStageEvent("assistant_delta", sessionName, delta', messenger_js)
        self.assertIn('await publishStageEvent("assistant_final", sessionName, stageMessage.text', messenger_js)
        self.assertIn("expression: stageMessage.expression", messenger_js)
        self.assertIn("motion: stageMessage.motion", messenger_js)
        self.assertIn('source: "messenger"', messenger_js)
        self.assertIn('"/api/stage/events"', messenger_js)

        self.assertIn("new EventSource(url)", stage_js)
        self.assertIn('source.addEventListener("assistant_delta"', stage_js)
        self.assertIn('source.addEventListener("assistant_final"', stage_js)
        self.assertIn('source.addEventListener("character_state"', stage_js)
        self.assertIn("applyStageVisualState(payload)", stage_js)
        self.assertIn("applyStageExpression", stage_js)
        self.assertIn("playStageMotion", stage_js)
        self.assertIn("subtitleElement.textContent", stage_js)
        self.assertNotIn("subtitleElement.innerHTML", stage_js)

        delta_handler = re.search(
            r'source\.addEventListener\("assistant_delta".*?\}\);',
            stage_js,
            flags=re.S,
        )
        final_handler = re.search(
            r'source\.addEventListener\("assistant_final".*?\}\);',
            stage_js,
            flags=re.S,
        )
        self.assertIsNotNone(delta_handler)
        self.assertIsNotNone(final_handler)
        self.assertNotIn("playTts", delta_handler.group(0))
        self.assertIn("playTts(payload.text)", final_handler.group(0))

    def test_stage_live2d_falls_back_before_noisy_webgl_initialization(self) -> None:
        stage_js = (WEB_ROOT / "stage-app.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn("canUsePixiLive2D()", stage_js)
        self.assertIn("canCreateWebGLShaderProgram()", stage_js)
        self.assertIn('"stage.fallback.webglUnavailable"', stage_js)
        self.assertIn("withPixiInitializationGuard", stage_js)
        self.assertIn("isKnownPixiInitializationNoise", stage_js)
        self.assertIn("destroyLive2DApp()", stage_js)
        self.assertIn('"stage.fallback.webglUnavailable"', i18n_js)

    def test_character_profiles_page_is_registered_and_translated(self) -> None:
        app_routes = (WEB_ROOT.parents[0] / "web_pages.py").read_text(encoding="utf-8")
        admin_html = (WEB_ROOT / "admin.html").read_text(encoding="utf-8")
        characters_html = (WEB_ROOT / "characters.html").read_text(encoding="utf-8")
        characters_js = (WEB_ROOT / "characters-app.js").read_text(encoding="utf-8")
        i18n_js = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

        self.assertIn('WebPageRoute("/admin/characters"', app_routes)
        self.assertIn('href="/admin/characters"', admin_html)
        self.assertIn('data-i18n-key="admin.characters"', admin_html)
        self.assertIn('id="character-profile-form"', characters_html)
        self.assertIn('id="character-model-profile"', characters_html)
        self.assertIn('"/api/character-profiles"', characters_js)
        self.assertIn('"characters.heading"', i18n_js)
        self.assertIn('"characters.modelProfile"', i18n_js)
        self.assertIn('"characters.effectiveProfile"', i18n_js)


if __name__ == "__main__":
    unittest.main()

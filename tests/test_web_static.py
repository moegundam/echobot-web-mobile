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


if __name__ == "__main__":
    unittest.main()

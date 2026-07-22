from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "echobot" / "app" / "web"
I18N_ROOT = WEB_ROOT / "i18n"


def _catalog_keys(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    return set(re.findall(r'^\s+"([^"]+)":\s*"', source, re.MULTILINE))


def _catalog_placeholders(path: Path) -> dict[str, tuple[str, ...]]:
    source = path.read_text(encoding="utf-8")
    result: dict[str, tuple[str, ...]] = {}
    for key, value in re.findall(r'^\s+"([^"]+)":\s*"((?:\\.|[^"\\])*)",?$', source, re.MULTILINE):
        result[key] = tuple(sorted(re.findall(r"\{([A-Za-z0-9_]+)\}", value)))
    return result


def test_shell_i18n_uses_three_separate_static_catalogs() -> None:
    catalogs = {
        "en": I18N_ROOT / "catalog-en.js",
        "zh-Hant": I18N_ROOT / "catalog-zh-Hant.js",
        "zh-Hans": I18N_ROOT / "catalog-zh-Hans.js",
    }

    assert all(path.is_file() for path in catalogs.values())
    assert all("export const" in path.read_text(encoding="utf-8") for path in catalogs.values())
    key_sets = {language: _catalog_keys(path) for language, path in catalogs.items()}
    assert key_sets["en"]
    assert key_sets["en"] == key_sets["zh-Hant"] == key_sets["zh-Hans"]
    assert len(key_sets["en"]) >= 900

    tracked_source = subprocess.check_output(
        ["git", "show", "HEAD:echobot/app/web/shell-i18n.js"],
        cwd=REPO_ROOT,
        text=True,
    )
    tracked_keys = set(re.findall(r'^\s+"([^"]+)":\s*"', tracked_source, re.MULTILINE))
    assert tracked_keys <= key_sets["en"]


def test_shell_i18n_facade_stays_small_and_preserves_public_entrypoint() -> None:
    source = (WEB_ROOT / "shell-i18n.js").read_text(encoding="utf-8")

    assert len(source.splitlines()) < 500
    assert re.search(r'import \{ en \} from "\./i18n/catalog-en\.js(?:\?[^\"]+)?";', source)
    assert re.search(r'import \{ zhHant \} from "\./i18n/catalog-zh-Hant\.js(?:\?[^\"]+)?";', source)
    assert re.search(r'import \{ zhHans \} from "\./i18n/catalog-zh-Hans\.js(?:\?[^\"]+)?";', source)
    assert "export function initShellI18n" in source
    assert "export const TRANSLATIONS" not in source
    assert "fetch(" not in source

    importers = [
        path
        for path in WEB_ROOT.rglob("*.js")
        if path.name != "shell-i18n.js" and "vendor" not in path.parts
    ]
    assert any('from "./shell-i18n.js' in path.read_text(encoding="utf-8") for path in importers)


def test_locale_catalogs_preserve_placeholder_semantics() -> None:
    paths = [
        I18N_ROOT / "catalog-en.js",
        I18N_ROOT / "catalog-zh-Hant.js",
        I18N_ROOT / "catalog-zh-Hans.js",
    ]
    placeholders = [_catalog_placeholders(path) for path in paths]

    assert placeholders[0]
    assert placeholders[0] == placeholders[1] == placeholders[2]


def test_all_literal_i18n_references_exist_in_catalogs() -> None:
    keys = _catalog_keys(I18N_ROOT / "catalog-en.js")
    literal_call = re.compile(
        r'(?<![A-Za-z0-9_])(?:i18n\.)?t\(\s*["\x27]([^"\x27]+)["\x27]',
    )
    references: dict[str, set[str]] = {}
    for path in WEB_ROOT.rglob("*.js"):
        if "vendor" in path.parts:
            continue
        for key in literal_call.findall(path.read_text(encoding="utf-8")):
            references.setdefault(key, set()).add(path.relative_to(WEB_ROOT).as_posix())

    missing = {
        key: sorted(paths)
        for key, paths in references.items()
        if key not in keys
    }
    assert not missing

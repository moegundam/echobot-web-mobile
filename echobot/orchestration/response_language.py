from __future__ import annotations


_LANGUAGE_ALIASES = {
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "english": "en",
    "zh-hant": "zh-Hant",
    "zh-tw": "zh-Hant",
    "zh-hk": "zh-Hant",
    "traditional": "zh-Hant",
    "traditional chinese": "zh-Hant",
    "繁體": "zh-Hant",
    "繁體中文": "zh-Hant",
    "zh-hans": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh-sg": "zh-Hans",
    "simplified": "zh-Hans",
    "simplified chinese": "zh-Hans",
    "简体": "zh-Hans",
    "简体中文": "zh-Hans",
}

_LANGUAGE_NAMES = {
    "en": "English",
    "zh-Hant": "Traditional Chinese (繁體中文)",
    "zh-Hans": "Simplified Chinese (简体中文)",
}


def normalize_response_language(language: str | None) -> str:
    text = str(language or "").strip()
    if not text:
        return ""
    return _LANGUAGE_ALIASES.get(text.lower(), text if text in _LANGUAGE_NAMES else "")


def response_language_instruction(language: str | None) -> str:
    normalized = normalize_response_language(language)
    if not normalized:
        return ""
    language_name = _LANGUAGE_NAMES[normalized]
    if normalized == "zh-Hant":
        language_detail = "Use Traditional Chinese characters and wording; do not reply in Simplified Chinese by default."
    elif normalized == "zh-Hans":
        language_detail = "Use Simplified Chinese characters and wording; do not reply in Traditional Chinese by default."
    else:
        language_detail = "Use English wording."
    return (
        f"Default response language: {language_name}. "
        f"{language_detail} "
        "If the user's latest prompt explicitly requests another response language, follow the prompt instead. "
        "Preserve quoted text, code, file paths, commands, JSON, logs, names, and source excerpts in their original language when needed."
    )

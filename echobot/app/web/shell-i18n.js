import { en } from "./i18n/catalog-en.js?v=uiux-2";
import { zhHant } from "./i18n/catalog-zh-Hant.js?v=uiux-2";
import { zhHans } from "./i18n/catalog-zh-Hans.js?v=uiux-2";

const LANGUAGE_STORAGE_KEY = "echobot.shell.language";
const DEFAULT_LANGUAGE = "en";

const LANGUAGES = [
    { code: "en", label: "English", htmlLang: "en" },
    { code: "zh-Hant", label: "繁體中文", htmlLang: "zh-Hant" },
    { code: "zh-Hans", label: "简体中文", htmlLang: "zh-Hans" },
];

const TRANSLATIONS = {
    en,
    "zh-Hant": zhHant,
    "zh-Hans": zhHans,
};

let languageMenuCounter = 0;
let languageMenuGlobalEventsBound = false;

export function initShellI18n({ onChange } = {}) {
    const controller = {
        language: resolveInitialLanguage(),
        t(key, params = {}) {
            return translate(controller.language, key, params);
        },
        apply() {
            applyStaticTranslations(controller);
        },
    };

    ensureLanguageSwitcher(controller, onChange);
    applyStaticTranslations(controller);
    return controller;
}

function resolveInitialLanguage() {
    const storedLanguage = readStoredLanguage();
    return isSupportedLanguage(storedLanguage) ? storedLanguage : DEFAULT_LANGUAGE;
}

function readStoredLanguage() {
    try {
        return String(window.localStorage.getItem(LANGUAGE_STORAGE_KEY) || "");
    } catch (_error) {
        return "";
    }
}

function writeStoredLanguage(language) {
    try {
        window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    } catch (_error) {
        // localStorage can be unavailable in restricted browsing contexts.
    }
}

function isSupportedLanguage(language) {
    return LANGUAGES.some((item) => item.code === language);
}

function translate(language, key, params = {}) {
    const bundle = TRANSLATIONS[language] || TRANSLATIONS[DEFAULT_LANGUAGE];
    const fallbackBundle = TRANSLATIONS[DEFAULT_LANGUAGE];
    const template = bundle[key] || fallbackBundle[key] || key;
    return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_match, name) => {
        return Object.prototype.hasOwnProperty.call(params, name)
            ? String(params[name])
            : "";
    });
}

function ensureLanguageSwitcher(controller, onChange) {
    const containers = Array.from(document.querySelectorAll("[data-language-switcher]"));
    if (containers.length === 0) {
        return;
    }

    bindLanguageMenuGlobalEvents();

    containers.forEach((container) => {
        const label = document.createElement("div");
        label.className = "shell-language-select-label";

        const labelText = document.createElement("span");
        labelText.dataset.i18nKey = "common.language";

        const picker = document.createElement("div");
        picker.className = "shell-language-picker";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "shell-language-select";
        button.setAttribute("aria-haspopup", "listbox");
        button.setAttribute("aria-expanded", "false");

        const value = document.createElement("span");
        value.className = "shell-language-select-value";

        const chevron = document.createElement("span");
        chevron.className = "shell-language-select-chevron";
        chevron.setAttribute("aria-hidden", "true");
        chevron.textContent = "v";

        const menuId = `shell-language-menu-${++languageMenuCounter}`;
        const menu = document.createElement("div");
        menu.id = menuId;
        menu.className = "shell-language-menu";
        menu.setAttribute("role", "listbox");
        menu.hidden = true;
        button.setAttribute("aria-controls", menuId);

        LANGUAGES.forEach((language) => {
            const option = document.createElement("button");
            option.type = "button";
            option.className = "shell-language-option";
            option.dataset.languageCode = language.code;
            option.setAttribute("role", "option");
            option.textContent = language.label;
            option.addEventListener("click", () => {
                setShellLanguage(controller, language.code, onChange);
                closeLanguageMenu(picker);
                button.focus();
            });
            option.addEventListener("keydown", (event) => {
                handleLanguageOptionKeydown(event, picker, option);
            });
            menu.appendChild(option);
        });

        button.append(value, chevron);
        button.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            toggleLanguageMenu(picker);
        });
        button.addEventListener("keydown", (event) => {
            if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                openLanguageMenu(picker);
            }
            if (event.key === "Escape") {
                closeLanguageMenu(picker);
            }
        });
        menu.addEventListener("click", (event) => {
            event.stopPropagation();
        });

        picker.append(button, menu);
        label.append(labelText, picker);
        container.replaceChildren(label);
    });

    syncLanguageSwitchers(controller);
}

function applyStaticTranslations(controller) {
    const languageConfig = LANGUAGES.find((item) => item.code === controller.language) || LANGUAGES[0];
    document.documentElement.lang = languageConfig.htmlLang;

    const titleKey = document.body && document.body.dataset.pageTitleKey;
    if (titleKey) {
        document.title = controller.t(titleKey);
    }

    document.querySelectorAll("[data-i18n-key]").forEach((node) => {
        node.textContent = controller.t(node.dataset.i18nKey);
    });
    document.querySelectorAll("[data-i18n-placeholder-key]").forEach((node) => {
        node.setAttribute("placeholder", controller.t(node.dataset.i18nPlaceholderKey));
    });
    document.querySelectorAll("[data-i18n-aria-label-key]").forEach((node) => {
        node.setAttribute("aria-label", controller.t(node.dataset.i18nAriaLabelKey));
    });
    document.querySelectorAll("[data-i18n-title-key]").forEach((node) => {
        node.setAttribute("title", controller.t(node.dataset.i18nTitleKey));
    });
    document.querySelectorAll("[data-i18n-alt-key]").forEach((node) => {
        node.setAttribute("alt", controller.t(node.dataset.i18nAltKey));
    });
    syncLanguageSwitchers(controller);
}

function setShellLanguage(controller, language, onChange) {
    const nextLanguage = isSupportedLanguage(language) ? language : DEFAULT_LANGUAGE;
    controller.language = nextLanguage;
    writeStoredLanguage(nextLanguage);
    applyStaticTranslations(controller);
    if (typeof onChange === "function") {
        onChange(nextLanguage);
    }
}

function bindLanguageMenuGlobalEvents() {
    if (languageMenuGlobalEventsBound) {
        return;
    }
    languageMenuGlobalEventsBound = true;
    document.addEventListener("click", () => {
        closeAllLanguageMenus();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeAllLanguageMenus();
        }
    });
}

function toggleLanguageMenu(picker) {
    const button = picker.querySelector(".shell-language-select");
    const isOpen = button && button.getAttribute("aria-expanded") === "true";
    if (isOpen) {
        closeLanguageMenu(picker);
        return;
    }
    openLanguageMenu(picker);
}

function openLanguageMenu(picker) {
    closeAllLanguageMenus(picker);
    const button = picker.querySelector(".shell-language-select");
    const menu = picker.querySelector(".shell-language-menu");
    if (!button || !menu) {
        return;
    }
    picker.classList.add("is-open");
    button.setAttribute("aria-expanded", "true");
    menu.hidden = false;
    queueMicrotask(() => {
        const selectedOption = menu.querySelector('.shell-language-option[aria-selected="true"]')
            || menu.querySelector(".shell-language-option");
        if (selectedOption) {
            selectedOption.focus();
        }
    });
}

function closeLanguageMenu(picker) {
    const button = picker.querySelector(".shell-language-select");
    const menu = picker.querySelector(".shell-language-menu");
    picker.classList.remove("is-open");
    if (button) {
        button.setAttribute("aria-expanded", "false");
    }
    if (menu) {
        menu.hidden = true;
    }
}

function closeAllLanguageMenus(exceptPicker = null) {
    document.querySelectorAll(".shell-language-picker.is-open").forEach((picker) => {
        if (picker !== exceptPicker) {
            closeLanguageMenu(picker);
        }
    });
}

function handleLanguageOptionKeydown(event, picker, option) {
    if (event.key === "Escape") {
        event.preventDefault();
        closeLanguageMenu(picker);
        const button = picker.querySelector(".shell-language-select");
        if (button) {
            button.focus();
        }
        return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Home" && event.key !== "End") {
        return;
    }
    event.preventDefault();
    const options = Array.from(picker.querySelectorAll(".shell-language-option"));
    const currentIndex = options.indexOf(option);
    let nextIndex = currentIndex;
    if (event.key === "ArrowDown") {
        nextIndex = currentIndex >= options.length - 1 ? 0 : currentIndex + 1;
    }
    if (event.key === "ArrowUp") {
        nextIndex = currentIndex <= 0 ? options.length - 1 : currentIndex - 1;
    }
    if (event.key === "Home") {
        nextIndex = 0;
    }
    if (event.key === "End") {
        nextIndex = options.length - 1;
    }
    if (options[nextIndex]) {
        options[nextIndex].focus();
    }
}

function syncLanguageSwitchers(controller) {
    const languageConfig = LANGUAGES.find((item) => item.code === controller.language) || LANGUAGES[0];
    document.querySelectorAll(".shell-language-picker").forEach((picker) => {
        const button = picker.querySelector(".shell-language-select");
        const value = picker.querySelector(".shell-language-select-value");
        if (value) {
            value.textContent = languageConfig.label;
        }
        if (button) {
            button.dataset.languageCode = languageConfig.code;
            button.setAttribute("aria-label", `${controller.t("common.language")}: ${languageConfig.label}`);
        }
        picker.querySelectorAll(".shell-language-option").forEach((option) => {
            const selected = option.dataset.languageCode === languageConfig.code;
            option.classList.toggle("is-selected", selected);
            option.setAttribute("aria-selected", selected ? "true" : "false");
        });
    });
}

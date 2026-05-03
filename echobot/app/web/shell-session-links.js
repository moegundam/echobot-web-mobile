export const SHELL_SESSION_STORAGE_KEY = "echobot.web.session";

export function initShellSessionLinks() {
    const sessionName = resolveShellSessionName();
    document.querySelectorAll("[data-session-link]").forEach((link) => {
        const href = link.getAttribute("href") || "";
        link.setAttribute("href", hrefWithSessionName(href, sessionName));
    });
}

export function rememberShellSessionName(sessionName) {
    const normalizedSessionName = normalizeSessionName(sessionName);
    try {
        window.localStorage.setItem(SHELL_SESSION_STORAGE_KEY, normalizedSessionName);
    } catch (_error) {
        // localStorage can be unavailable in restricted browsing contexts.
    }
    return normalizedSessionName;
}

export function resolveShellSessionName() {
    const params = new URLSearchParams(window.location.search);
    if (params.has("session_name")) {
        const querySessionName = normalizeSessionName(params.get("session_name"));
        rememberShellSessionName(querySessionName);
        return querySessionName;
    }

    try {
        const storedSessionName = normalizeSessionName(
            window.localStorage.getItem(SHELL_SESSION_STORAGE_KEY),
        );
        if (storedSessionName) {
            return storedSessionName;
        }
    } catch (_error) {
        // Fall through to the default session.
    }

    return "default";
}

function hrefWithSessionName(href, sessionName) {
    try {
        const url = new URL(href, window.location.origin);
        url.searchParams.set("session_name", sessionName);
        return `${url.pathname}${url.search}${url.hash}`;
    } catch (_error) {
        return href;
    }
}

function normalizeSessionName(sessionName) {
    return String(sessionName || "").trim() || "default";
}

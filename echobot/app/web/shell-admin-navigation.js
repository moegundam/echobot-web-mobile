const DESKTOP_NAVIGATION_QUERY = "(min-width: 768px)";
const ADMIN_PAGE_LABELS = {
    "/admin/sessions": ["admin.sessions", "Sessions"],
    "/admin/characters": ["admin.characters", "Characters"],
    "/admin/models": ["admin.llmModels", "LLM Models"],
    "/admin/voice-models": ["admin.voiceModels", "Voice Models"],
    "/admin/live2d": ["admin.live2d", "Live2D"],
    "/admin/channels": ["admin.channels", "Channels"],
    "/admin/openwebui": ["admin.openwebui", "Open WebUI Bridge"],
    "/admin/guide": ["admin.guide", "Operation Guide"],
    "/admin/structure": ["admin.structure", "Site Structure"],
    "/admin/deployment": ["admin.deployment", "Deployment"],
};

export function initAdminNavigation() {
    if (!normalizedPath(window.location.pathname).startsWith("/admin")) {
        return;
    }
    document.querySelectorAll(".guide-nav").forEach((nav) => {
        if (nav.closest(".admin-nav-disclosure")) {
            return;
        }

        const currentPath = normalizedPath(window.location.pathname);
        let currentLink = null;
        nav.querySelectorAll("a[href]").forEach((link) => {
            const linkPath = normalizedPath(new URL(link.href, window.location.href).pathname);
            if (linkPath !== currentPath) {
                return;
            }
            link.setAttribute("aria-current", "page");
            currentLink = link;
        });
        if (!currentLink && ADMIN_PAGE_LABELS[currentPath]) {
            currentLink = createCurrentPageLink(currentPath, ADMIN_PAGE_LABELS[currentPath]);
            const adminIndexLink = Array.from(nav.querySelectorAll("a[href]")).find(
                (link) => normalizedPath(new URL(link.href, window.location.href).pathname) === "/admin",
            );
            if (adminIndexLink) {
                adminIndexLink.after(currentLink);
            } else {
                nav.prepend(currentLink);
            }
        }

        const disclosure = document.createElement("details");
        disclosure.className = "admin-nav-disclosure";
        const summary = document.createElement("summary");
        summary.className = "admin-nav-summary";

        const label = document.createElement("span");
        label.setAttribute("data-i18n-key", "admin.navigation");
        label.textContent = "Admin navigation";
        const current = document.createElement("strong");
        const currentI18nKey = currentLink && currentLink.dataset.i18nKey;
        current.setAttribute("data-i18n-key", currentI18nKey || "admin.navigation");
        current.textContent = currentLink ? currentLink.textContent.trim() : label.textContent;
        summary.append(label, current);

        const media = window.matchMedia(DESKTOP_NAVIGATION_QUERY);
        disclosure.open = media.matches;
        let userSelectedState = false;
        summary.addEventListener("click", () => {
            userSelectedState = true;
        });
        media.addEventListener?.("change", (event) => {
            if (!userSelectedState) {
                disclosure.open = event.matches;
            }
        });

        nav.before(disclosure);
        disclosure.append(summary, nav);
    });
}

function createCurrentPageLink(pathname, labelConfig) {
    const [i18nKey, fallbackLabel] = labelConfig;
    const link = document.createElement("a");
    link.href = pathname;
    link.setAttribute("data-i18n-key", i18nKey);
    link.setAttribute("aria-current", "page");
    link.textContent = fallbackLabel;
    return link;
}

function normalizedPath(pathname) {
    const normalized = String(pathname || "/").replace(/\/+$/, "");
    return normalized || "/";
}

initAdminNavigation();

const ROUTE_MODE_VALUES = new Set(["auto", "chat_only", "force_agent"]);

export function normalizeRouteMode(routeMode) {
    const value = String(routeMode || "").trim().toLowerCase();
    if (value === "agent") {
        return "force_agent";
    }
    return ROUTE_MODE_VALUES.has(value) ? value : "auto";
}

export function routeModeLabel(routeMode, t = null) {
    const translate = typeof t === "function" ? t : null;
    if (routeMode === "chat_only") {
        return translate ? translate("console.routeChatOnly") : "Chat only";
    }
    if (routeMode === "force_agent") {
        return translate ? translate("console.routeForceAgent") : "Force Agent";
    }
    return translate ? translate("console.routeAuto") : "Auto decision";
}

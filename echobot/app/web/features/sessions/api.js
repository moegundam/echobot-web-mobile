export function createSessionsApi(deps) {
    const { requestJson } = deps;

    async function requestSessionSummaries() {
        const payload = await requestJson("/api/sessions");
        return Array.isArray(payload) ? payload : [];
    }

    async function requestSessionDetail(sessionName) {
        return await requestJson(`/api/sessions/${encodeURIComponent(sessionName)}`);
    }

    async function switchCurrentSession(sessionName) {
        return await requestJson("/api/sessions/current", {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ name: sessionName }),
        });
    }

    async function updateSessionRole(sessionName, roleName) {
        return await requestJson(
            `/api/sessions/${encodeURIComponent(sessionName)}/role`,
            {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ role_name: roleName }),
            },
        );
    }

    async function updateSessionRouteMode(sessionName, routeMode) {
        return await requestJson(
            `/api/sessions/${encodeURIComponent(sessionName)}/route-mode`,
            {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ route_mode: routeMode }),
            },
        );
    }

    return {
        requestSessionDetail: requestSessionDetail,
        requestSessionSummaries: requestSessionSummaries,
        switchCurrentSession: switchCurrentSession,
        updateSessionRole: updateSessionRole,
        updateSessionRouteMode: updateSessionRouteMode,
    };
}

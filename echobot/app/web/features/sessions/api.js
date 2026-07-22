export function createSessionsApi(deps) {
    const { requestJson } = deps;

    async function requestSessionSummaries() {
        const payload = await requestJson("/api/sessions");
        return Array.isArray(payload) ? payload : [];
    }

    async function requestSessionDetail(sessionName) {
        return await requestJson(`/api/sessions/${encodeURIComponent(sessionName)}`);
    }

    async function requestSessionRuntimeContext(sessionName) {
        return await requestJson(
            `/api/sessions/${encodeURIComponent(sessionName)}/runtime-context`,
        );
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

    async function updateSessionRuntimeOverrides(sessionName, overrides) {
        return await requestJson(
            `/api/sessions/${encodeURIComponent(sessionName)}/runtime-overrides`,
            {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(overrides || {}),
            },
        );
    }

    return {
        requestSessionDetail: requestSessionDetail,
        requestSessionRuntimeContext: requestSessionRuntimeContext,
        requestSessionSummaries: requestSessionSummaries,
        switchCurrentSession: switchCurrentSession,
        updateSessionRuntimeOverrides: updateSessionRuntimeOverrides,
        updateSessionRole: updateSessionRole,
        updateSessionRouteMode: updateSessionRouteMode,
    };
}

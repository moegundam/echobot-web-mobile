export function createStageEventController({
    getSessionName,
    announceSubtitle,
    setStatus,
    appendSubtitle,
    setSubtitle,
    applyVisualState,
    refreshStageContext,
    playTts,
}) {
    let stageEventSource = null;

    function close() {
        if (stageEventSource) {
            stageEventSource.close();
            stageEventSource = null;
        }
    }

    function init() {
        if (!window.EventSource) {
            setStatus("stage.status.sseUnavailable");
            return;
        }
        close();

        const sessionName = getSessionName();
        const url = `/api/stage/events?session_name=${encodeURIComponent(sessionName)}`;
        const sourceSessionName = sessionName;
        const source = new EventSource(url);
        stageEventSource = source;

        source.addEventListener("open", () => {
            if (source !== stageEventSource || sourceSessionName !== getSessionName()) {
                return;
            }
            setStatus("stage.status.live");
        });
        source.addEventListener("error", () => {
            if (source !== stageEventSource || sourceSessionName !== getSessionName()) {
                return;
            }
            setStatus("stage.status.reconnecting");
        });
        source.addEventListener("assistant_delta", (event) => {
            if (source !== stageEventSource || sourceSessionName !== getSessionName()) {
                return;
            }
            const payload = parseStageEvent(event);
            appendSubtitle(payload.text);
        });
        source.addEventListener("subtitle", (event) => {
            if (source !== stageEventSource || sourceSessionName !== getSessionName()) {
                return;
            }
            const payload = parseStageEvent(event);
            applyVisualState(payload);
            setSubtitle(payload.text);
            announceSubtitle(payload.text);
        });
        source.addEventListener("assistant_final", async (event) => {
            if (source !== stageEventSource || sourceSessionName !== getSessionName()) {
                return;
            }
            const payload = parseStageEvent(event);
            applyVisualState(payload);
            setSubtitle(payload.text);
            announceSubtitle(payload.text);
            await playTts(payload.text);
        });
        source.addEventListener("character_state", (event) => {
            if (source !== stageEventSource || sourceSessionName !== getSessionName()) {
                return;
            }
            const payload = parseStageEvent(event);
            applyVisualState(payload);
        });
        source.addEventListener("runtime_context_changed", (event) => {
            if (source !== stageEventSource || sourceSessionName !== getSessionName()) {
                return;
            }
            const payload = parseStageEvent(event);
            void refreshStageContext({
                reloadLive2D: true,
                expectedRevision: payload.revision,
            });
        });
    }

    return {
        close,
        init,
    };
}


function parseStageEvent(event) {
    try {
        const payload = JSON.parse(event.data || "{}");
        const metadata = payload && typeof payload.metadata === "object" && payload.metadata
            ? payload.metadata
            : {};
        return {
            text: String(payload.text || ""),
            emotion: String(payload.emotion || metadata.emotion || ""),
            expression: String(payload.expression || metadata.expression || ""),
            motion: String(payload.motion || metadata.motion || ""),
            revision: String(metadata.revision || ""),
        };
    } catch (_error) {
        return {
            text: "",
            emotion: "",
            expression: "",
            motion: "",
            revision: "",
        };
    }
}

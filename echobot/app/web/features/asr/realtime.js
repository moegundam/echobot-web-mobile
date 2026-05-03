import { asrState } from "../../core/store.js";

const FLUSH_TIMEOUT_MS = 800;
const SOCKET_OPEN_TIMEOUT_MS = 8000;

export function createRealtimeAsrClient(deps) {
    const {
        onEvent,
        onUnexpectedClose,
        t = (key) => key,
    } = deps;

    let flushResolver = null;

    async function open() {
        if (asrState.asrSocket && asrState.asrSocket.readyState <= WebSocket.OPEN) {
            return;
        }

        const socket = new WebSocket(buildAsrSocketUrl());
        socket.binaryType = "arraybuffer";
        socket.addEventListener("message", handleSocketMessage);
        socket.addEventListener("close", handleSocketClose);
        socket.addEventListener("error", (error) => {
            console.error("ASR websocket error", error);
        });

        try {
            await waitForSocketOpen(socket, t);
        } catch (error) {
            asrState.asrSocketIntentionalClose = true;
            try {
                socket.close();
            } catch (closeError) {
                console.warn("ASR websocket close ignored", closeError);
            }
            throw error;
        }

        asrState.asrSocketIntentionalClose = false;
        asrState.asrSocket = socket;
    }

    async function close(options = {}) {
        const { flushFirst = false } = options;
        const socket = asrState.asrSocket;
        if (!socket) {
            return;
        }

        if (flushFirst && socket.readyState === WebSocket.OPEN) {
            await flush(socket);
        }

        asrState.asrSocketIntentionalClose = true;
        asrState.asrSocket = null;
        resolvePendingFlush();
        try {
            socket.close();
        } catch (error) {
            console.warn("ASR websocket close ignored", error);
        }
    }

    function sendControl(command) {
        if (!asrState.asrSocket || asrState.asrSocket.readyState !== WebSocket.OPEN) {
            return;
        }
        asrState.asrSocket.send(String(command || ""));
    }

    function sendChunk(int16Chunk) {
        if (!asrState.asrSocket || asrState.asrSocket.readyState !== WebSocket.OPEN) {
            return;
        }
        asrState.asrSocket.send(
            int16Chunk.buffer.slice(
                int16Chunk.byteOffset,
                int16Chunk.byteOffset + int16Chunk.byteLength,
            ),
        );
    }

    return {
        close: close,
        open: open,
        sendChunk: sendChunk,
        sendControl: sendControl,
    };

    async function flush(socket) {
        if (flushResolver) {
            resolvePendingFlush();
        }

        const flushPromise = new Promise((resolve) => {
            flushResolver = resolve;
        });
        socket.send("flush");
        await Promise.race([flushPromise, waitTimeout(FLUSH_TIMEOUT_MS)]);
        resolvePendingFlush();
    }

    function handleSocketMessage(event) {
        if (!event || typeof event.data !== "string") {
            return;
        }

        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch (error) {
            console.warn("Failed to parse ASR websocket payload", error);
            return;
        }

        if (payload.type === "flush_complete") {
            resolvePendingFlush();
            return;
        }

        onEvent(payload);
    }

    function handleSocketClose() {
        const intentional = asrState.asrSocketIntentionalClose;
        asrState.asrSocket = null;
        asrState.asrSocketIntentionalClose = false;
        resolvePendingFlush();

        if (!intentional) {
            onUnexpectedClose();
        }
    }

    function resolvePendingFlush() {
        if (!flushResolver) {
            return;
        }

        const resolve = flushResolver;
        flushResolver = null;
        resolve();
    }
}

function buildAsrSocketUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/web/asr/ws`;
}

function waitForSocketOpen(socket, t) {
    return new Promise((resolve, reject) => {
        const timerId = window.setTimeout(() => {
            reject(new Error(t("console.realtimeAsrTimeout")));
        }, SOCKET_OPEN_TIMEOUT_MS);

        socket.addEventListener(
            "open",
            () => {
                window.clearTimeout(timerId);
                resolve();
            },
            { once: true },
        );
        socket.addEventListener(
            "error",
            () => {
                window.clearTimeout(timerId);
                reject(new Error(t("console.realtimeAsrConnectionFailed")));
            },
            { once: true },
        );
    });
}

function waitTimeout(timeoutMs) {
    return new Promise((resolve) => {
        window.setTimeout(resolve, timeoutMs);
    });
}

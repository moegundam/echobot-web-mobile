export async function requestJson(url, options = {}) {
    const requestInit = { ...options };
    const providedHeaders = options.headers || {};
    const hasContentType = Boolean(
        providedHeaders["Content-Type"] || providedHeaders["content-type"],
    );
    requestInit.headers = {
        Accept: "application/json",
        ...(typeof requestInit.body === "string" && !hasContentType
            ? { "Content-Type": "application/json" }
            : {}),
        ...providedHeaders,
    };

    const response = await fetch(url, requestInit);
    if (!response.ok) {
        throw await responseToError(response);
    }
    if (response.status === 204) {
        return null;
    }
    return await response.json();
}

export async function uploadChatImage(file) {
    const formData = new FormData();
    formData.append("file", file);
    return await requestJson("/api/attachments/images", {
        method: "POST",
        body: formData,
    });
}

export async function uploadChatFile(file) {
    const formData = new FormData();
    formData.append("file", file);
    return await requestJson("/api/attachments/files", {
        method: "POST",
        body: formData,
    });
}

export async function deleteAttachment(attachmentId) {
    const response = await fetch(`/api/attachments/${encodeURIComponent(attachmentId)}`, {
        method: "DELETE",
    });
    if (!response.ok) {
        throw await responseToError(response);
    }
}

export async function requestChatStream(payload, handlers, options = {}) {
    const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        signal: options.signal,
    });

    if (!response.ok) {
        throw await responseToError(response);
    }

    if (!response.body) {
        if (options.allowFallback === false) {
            throw new Error(
                options.streamUnavailableMessage || "Chat stream is unavailable.",
            );
        }
        const finalPayload = await requestJson("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
            signal: options.signal,
        });
        if (handlers && typeof handlers.onDone === "function") {
            await handlers.onDone(finalPayload);
        }
        return finalPayload;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalPayload = null;

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }

        buffer += decoder.decode(value, { stream: true });
        const parsed = await consumeChatStreamBuffer(buffer, handlers);
        buffer = parsed.buffer;
        if (parsed.finalPayload) {
            finalPayload = parsed.finalPayload;
        }
    }

    buffer += decoder.decode();
    const parsed = await consumeChatStreamBuffer(
        buffer ? `${buffer}\n` : buffer,
        handlers,
    );
    if (parsed.finalPayload) {
        finalPayload = parsed.finalPayload;
    }

    if (!finalPayload) {
        throw new Error(
            options.streamEndedMessage || "Chat stream ended without a final response.",
        );
    }
    if (handlers && typeof handlers.onDone === "function") {
        await handlers.onDone(finalPayload);
    }

    return finalPayload;
}

export async function requestChatJob(jobId) {
    return await requestJson(`/api/chat/jobs/${encodeURIComponent(jobId)}`);
}

export async function requestChatJobTrace(jobId) {
    return await requestJson(`/api/chat/jobs/${encodeURIComponent(jobId)}/trace`);
}

export async function cancelChatJob(jobId) {
    return await requestJson(
        `/api/chat/jobs/${encodeURIComponent(jobId)}/cancel`,
        {
            method: "POST",
        },
    );
}

export async function consumeChatStreamBuffer(buffer, handlers) {
    let remaining = buffer;
    let finalPayload = null;

    while (true) {
        const newlineIndex = remaining.indexOf("\n");
        if (newlineIndex === -1) {
            break;
        }

        const line = remaining.slice(0, newlineIndex).trim();
        remaining = remaining.slice(newlineIndex + 1);
        if (!line) {
            continue;
        }

        let event;
        try {
            event = JSON.parse(line);
        } catch (_error) {
            throw new Error(`Invalid chat stream event: ${line}`);
        }

        if (event.type === "chunk") {
            if (handlers && typeof handlers.onChunk === "function") {
                await handlers.onChunk(event.delta || "");
            }
            continue;
        }
        if (event.type === "done") {
            finalPayload = event;
            continue;
        }
        if (event.type === "error") {
            throw new Error(event.message || "Chat stream failed.");
        }
    }

    return {
        buffer: remaining,
        finalPayload: finalPayload,
    };
}

export async function responseToError(response) {
    let detail = `${response.status} ${response.statusText}`;
    let code = "";
    try {
        const payload = await response.json();
        if (payload && typeof payload.detail === "string") {
            detail = payload.detail;
        }
        if (payload && typeof payload.code === "string") {
            code = payload.code;
        }
    } catch (error) {
        console.warn("Non-JSON error response", error);
    }
    const requestError = new Error(detail);
    requestError.status = response.status;
    requestError.code = code;
    return requestError;
}

export function requestErrorMessage(error, t, fallbackKey) {
    const status = Number(error && error.status || 0);
    if (status === 401) {
        return t("errors.authenticationRequired");
    }
    if (status === 403) {
        return t("errors.permissionDenied");
    }
    if (status >= 500) {
        return t("errors.serverUnavailable", { status });
    }
    const detail = String(error && error.message || "").trim();
    return detail || t(fallbackKey);
}

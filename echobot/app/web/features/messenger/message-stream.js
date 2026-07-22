const DEFAULT_STAGE_DIRECTIVE_PATTERN = /^\s*\[(emotion|expression|motion)\s*[:=]\s*([^\]\r\n]{1,256})\]\s*/i;

export function createMessengerMessageController({
    input,
    urlInput,
    i18n,
    setStatus,
    setBusy,
    getBusy,
    getPendingAttachments,
    clearPendingAttachments,
    renderPendingAttachments,
    getAttachmentUploadPromise,
    currentSessionName,
    selectedSessionName,
    activeRouteMode,
    getResponseLanguagePayload,
    getSendToken,
    appendMessage,
    scrollMessagesIfNearBottom,
    publishStageStreamStart,
    publishStageDelta,
    publishStageFinal,
    streamChat,
}) {
    async function submitMessage(abortController, sendToken) {
        if (getBusy()) {
            return;
        }
        setBusy(true);
        const attachmentUploadPromise = getAttachmentUploadPromise();
        if (attachmentUploadPromise) {
            await attachmentUploadPromise;
        }
        const attachments = [...getPendingAttachments()];
        const prompt = promptWithUrl(
            String((input && input.value) || "").trim(),
            String((urlInput && urlInput.value) || "").trim(),
        );
        const messagePrompt = prompt || (
            attachments.length > 0 ? i18n.t("messenger.attachmentOnlyPrompt") : ""
        );
        if (!messagePrompt) {
            setBusy(false);
            return;
        }

        const sessionName = currentSessionName();
        appendMessage("user", messagePrompt);
        if (input) {
            input.value = "";
        }
        if (urlInput) {
            urlInput.value = "";
        }
        clearPendingAttachments();
        renderPendingAttachments();

        const assistantNode = appendMessage("assistant", "");
        let assistantText = "";
        setStatus("messenger.status.streaming");

        try {
            await publishStageStreamStart(sessionName);
            await streamChat(
                {
                    prompt: messagePrompt,
                    session_name: sessionName,
                    route_mode: activeRouteMode(sessionName),
                    ...getResponseLanguagePayload(),
                    images: attachments
                        .filter((item) => item.kind === "image")
                        .map((item) => ({ attachment_id: item.attachment_id })),
                    files: attachments
                        .filter((item) => item.kind === "file")
                        .map((item) => ({ attachment_id: item.attachment_id })),
                },
                {
                    onChunk: async (delta) => {
                        if (
                            sendToken !== getSendToken()
                            || sessionName !== selectedSessionName()
                        ) {
                            return;
                        }
                        assistantText += delta;
                        scrollMessagesIfNearBottom(() => {
                            assistantNode.textContent = assistantText;
                        });
                        await publishStageDelta(sessionName, delta);
                    },
                    onDone: async (event) => {
                        if (
                            sendToken !== getSendToken()
                            || sessionName !== selectedSessionName()
                        ) {
                            return;
                        }
                        const finalText = String(
                            event.response || event.response_content || assistantText || "",
                        );
                        const stageMessage = extractStageDirectives(finalText);
                        assistantText = stageMessage.text;
                        scrollMessagesIfNearBottom(() => {
                            assistantNode.textContent = stageMessage.text;
                        });
                        await publishStageFinal(sessionName, stageMessage);
                    },
                },
                abortController.signal,
            );
            setStatus("messenger.status.ready");
        } catch (error) {
            if (abortController.signal.aborted) {
                return;
            }
            console.error(error);
            assistantNode.textContent = `${i18n.t("messenger.errorPrefix")}：${error.message || error}`;
            setStatus("messenger.status.error");
        } finally {
            setBusy(false);
        }
    }

    return { submitMessage };
}

export function promptWithUrl(rawPrompt, rawUrl) {
    const prompt = String(rawPrompt || "").trim();
    const url = String(rawUrl || "").trim();
    if (!url) {
        return prompt;
    }
    const urlBlock = `URL:\n${url}`;
    return prompt ? `${prompt}\n\n${urlBlock}` : urlBlock;
}

export function extractStageDirectives(
    text,
    stageDirectivePattern = DEFAULT_STAGE_DIRECTIVE_PATTERN,
) {
    const directives = {
        text: String(text || ""),
        emotion: "",
        expression: "",
        motion: "",
    };
    let remaining = directives.text;

    while (true) {
        const match = remaining.match(stageDirectivePattern);
        if (!match) {
            break;
        }
        const key = String(match[1] || "").toLowerCase();
        const value = String(match[2] || "").trim();
        if (key && Object.prototype.hasOwnProperty.call(directives, key)) {
            directives[key] = value;
        }
        remaining = remaining.slice(match[0].length);
    }

    directives.text = remaining.trimStart();
    return directives;
}

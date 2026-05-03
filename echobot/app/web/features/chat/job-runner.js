import { DOM } from "../../core/dom.js";
import { audioState, chatState, roleState, sessionState } from "../../core/store.js";
import {
    buildUserMessageContent,
    hasMessageContent,
    messageContentToText,
} from "../../modules/content.js";

export function createChatRunner(deps) {
    const {
        addMessage,
        applySessionSummaries,
        cancelChatJob,
        clearComposerAttachments,
        createSpeechSession,
        drainVoicePromptQueue,
        ensureAudioContextReady,
        finalizeSpeechSession,
        normalizeSessionName,
        queueSpeechSessionText,
        removeMessage,
        requestChatJob,
        requestChatJobTrace,
        requestChatStream,
        requestSessionSummaries,
        resetTracePanel,
        setActiveBackgroundJob,
        setChatBusy,
        setRunStatus,
        speakText,
        startTracePanel,
        stopSpeechPlayback,
        syncCurrentSessionFromServer,
        t = (key) => key,
        applyTracePayload,
        updateMessage,
    } = deps;

    async function handleChatSubmit(event) {
        event.preventDefault();
        if (chatState.chatBusy) {
            return;
        }

        const prompt = String(DOM.promptInput?.value || "").trim();
        const composerImages = [...(chatState.composerImages || [])];
        const composerFiles = [...(chatState.composerFiles || [])];
        if (!prompt && composerImages.length === 0 && composerFiles.length === 0) {
            return;
        }

        await ensureAudioContextReady();

        const sessionName = normalizeSessionName(
            sessionState.currentSessionName || "",
        );
        sessionState.currentSessionName = sessionName;
        DOM.sessionLabel.textContent = t("console.sessionLabel", { session: sessionName });
        window.localStorage.setItem("echobot.web.session", sessionName);

        stopSpeechPlayback();
        setActiveBackgroundJob("");
        resetTracePanel();
        setChatBusy(true);
        const speechSession = audioState.ttsEnabled ? createSpeechSession() : null;
        setRunStatus(t("console.requestingReply"));

        addMessage(
            "user",
            buildUserMessageContent(
                prompt,
                composerImages.map((image) => ({
                    attachment_id: image.attachmentId,
                    url: image.url,
                    preview_url: image.previewUrl,
                })),
                composerFiles.map((file) => ({
                    attachment_id: file.attachmentId,
                    download_url: file.downloadUrl,
                    name: file.name,
                    content_type: file.contentType,
                    size_bytes: file.sizeBytes,
                    workspace_path: file.workspacePath,
                })),
            ),
            t("console.youLabel"),
            { renderMode: "plain", labelKey: "console.youLabel" },
        );
        let assistantMessageId = addMessage(
            "assistant",
            t("console.loadingEllipsis"),
            t("console.echoLabel"),
            { renderMode: "plain", labelKey: "console.echoLabel" },
        );
        let streamedText = "";

        try {
            const response = await requestChatStream(
                {
                    prompt,
                    session_name: sessionName,
                    role_name: roleState.currentRoleName || "default",
                    route_mode: sessionState.currentRouteMode || "auto",
                    images: composerImages.map((image) => ({
                        attachment_id: image.attachmentId,
                    })),
                    files: composerFiles.map((file) => ({
                        attachment_id: file.attachmentId,
                    })),
                },
                {
                    onChunk(delta) {
                        streamedText += delta;
                        updateMessage(
                            assistantMessageId,
                            streamedText || t("console.loadingEllipsis"),
                            t("console.echoLabel"),
                            { renderMode: "plain", labelKey: "console.echoLabel" },
                        );
                        queueSpeechSessionText(speechSession, delta);
                    },
                },
            );
            DOM.promptInput.value = "";
            clearComposerAttachments();

            if (response.session_name) {
                sessionState.currentSessionName = normalizeSessionName(response.session_name);
                DOM.sessionLabel.textContent = t("console.sessionLabel", { session: sessionState.currentSessionName });
                window.localStorage.setItem("echobot.web.session", sessionState.currentSessionName);
            }
            roleState.currentRoleName = response.role_name || roleState.currentRoleName;

            const immediateContent = response.response_content ?? response.response ?? streamedText ?? "";
            const immediateText = messageContentToText(
                immediateContent,
                { includeImageMarker: false },
            ).trim();
            const hideImmediateReply = Boolean(
                response.job_id
                && response.status === "running"
                && !hasMessageContent(immediateContent),
            );
            let finalContent = immediateContent;
            let finalText = immediateText || t("console.processing");
            let speakFinalText = true;
            const startupSpeech = hideImmediateReply
                ? Promise.resolve()
                : finalizeSpeechSession(speechSession, finalText);
            if (hideImmediateReply) {
                removeMessage(assistantMessageId);
                assistantMessageId = "";
                finalText = "";
            } else {
                updateMessage(
                    assistantMessageId,
                    finalContent,
                    response.completed ? t("console.echoLabel") : t("console.processing"),
                    response.completed ? { labelKey: "console.echoLabel" } : {},
                );
            }

            if (response.job_id && response.status === "running") {
                setActiveBackgroundJob(response.job_id);
                setRunStatus(t("console.agentRunningInBackground"));
                startTracePanel(response.job_id);

                const finalJob = await pollChatJob(response.job_id);
                finalContent = finalJob.response_content ?? finalJob.response ?? finalContent;
                finalText = messageContentToText(
                    finalContent,
                    { includeImageMarker: false },
                ).trim() || t("console.jobEndedNoContent");
                if (assistantMessageId) {
                    updateMessage(assistantMessageId, finalContent, t("console.echoLabel"), {
                        labelKey: "console.echoLabel",
                    });
                } else {
                    assistantMessageId = addMessage("assistant", finalContent, t("console.echoLabel"), {
                        labelKey: "console.echoLabel",
                    });
                }

                await startupSpeech;
                if (finalText === immediateText || finalJob.status === "cancelled") {
                    speakFinalText = false;
                }

                if (finalJob.status === "cancelled") {
                    setRunStatus(t("console.backgroundJobStopped"));
                } else if (finalJob.status === "waiting_for_input") {
                    setRunStatus(t("console.waitingForYourInput"));
                } else if (finalJob.status === "failed") {
                    setRunStatus(t("console.backgroundJobFailed"));
                } else {
                    setRunStatus(t("console.replyCompleted"));
                }
            } else {
                speakFinalText = false;
                setRunStatus(t("console.replyCompleted"));
            }

            if (audioState.ttsEnabled && speakFinalText && finalText.trim()) {
                await speakText(finalText);
            }

            try {
                applySessionSummaries(await requestSessionSummaries());
            } catch (sessionError) {
                console.error("Failed to refresh session list after chat", sessionError);
            }
            await syncCurrentSessionFromServer({
                force: true,
                announceNewMessages: false,
            });
        } catch (error) {
            console.error(error);
            stopSpeechPlayback();
            if (assistantMessageId && !streamedText.trim()) {
                removeMessage(assistantMessageId);
            }
            addMessage("system", `${t("console.requestFailed")}: ${error.message || error}`, t("console.systemLabel"), {
                labelKey: "console.systemLabel",
            });
            setRunStatus(error.message || t("console.requestFailed"));
        } finally {
            setActiveBackgroundJob("");
            setChatBusy(false);
            void drainVoicePromptQueue();
        }
    }

    async function pollChatJob(jobId) {
        const maxAttempts = 240;

        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            const [payload, tracePayload] = await Promise.all([
                requestChatJob(jobId),
                loadChatJobTrace(jobId),
            ]);
            if (tracePayload) {
                applyTracePayload(jobId, tracePayload);
            }
            if (payload.status !== "running") {
                return payload;
            }
            await new Promise((resolve) => {
                window.setTimeout(resolve, 1000);
            });
        }

        throw new Error(t("console.backgroundJobTimeout"));
    }

    async function loadChatJobTrace(jobId) {
        try {
            return await requestChatJobTrace(jobId);
        } catch (error) {
            console.warn("Failed to load agent trace", error);
            return null;
        }
    }

    async function handleStopBackgroundJob() {
        const jobId = chatState.activeChatJobId;
        if (!jobId) {
            return;
        }

        if (DOM.stopAgentButton) {
            DOM.stopAgentButton.disabled = true;
        }
        setRunStatus(t("console.stoppingBackgroundJob"));

        try {
            const payload = await cancelChatJob(jobId);
            if (payload.status === "cancelled") {
                setRunStatus(t("console.backgroundJobStopped"));
                return;
            }
            if (payload.status === "completed") {
                setRunStatus(t("console.backgroundJobCompleted"));
                return;
            }
            if (payload.status === "failed") {
                setRunStatus(t("console.backgroundJobFailed"));
                return;
            }
            if (payload.status === "waiting_for_input") {
                setRunStatus(t("console.waitingForYourInput"));
                return;
            }

            if (DOM.stopAgentButton) {
                DOM.stopAgentButton.disabled = false;
            }
        } catch (error) {
            console.error(error);
            if (DOM.stopAgentButton) {
                DOM.stopAgentButton.disabled = false;
            }
            addMessage("system", `${t("console.stopBackgroundJobFailed")}: ${error.message || error}`, t("console.systemLabel"), {
                labelKey: "console.systemLabel",
            });
            setRunStatus(error.message || t("console.stopBackgroundJobFailed"));
        }
    }

    return {
        handleChatSubmit,
        handleStopBackgroundJob,
    };
}

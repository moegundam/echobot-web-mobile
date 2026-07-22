import { requestJson, responseToError } from "../../modules/api.js";


export async function fetchStageTargets() {
    return await requestJson("/api/channels/stage-targets");
}


export async function fetchStageSessions() {
    return await requestJson("/api/sessions");
}


export async function fetchStageWebConfig() {
    return await requestJson("/api/web/config");
}


export async function synthesizeStageTts(requestBody, options = {}) {
    const response = await fetch("/api/web/tts", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
        signal: options.signal,
    });
    if (!response.ok) {
        throw await responseToError(response);
    }
    return await response.blob();
}

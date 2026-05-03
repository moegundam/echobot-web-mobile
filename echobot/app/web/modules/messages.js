import { DOM } from "../core/dom.js";
import { messageState } from "../core/store.js";
import {
    FILE_ATTACHMENT_CONTENT_BLOCK_TYPE,
    IMAGE_URL_CONTENT_BLOCK_TYPE,
    TEXT_CONTENT_BLOCK_TYPE,
    normalizeMessageContent,
} from "./content.js";
import {
    clearMathTypesetting,
    scheduleMathTypesetting,
} from "./math.js";
import {
    buildMarkdownFragment,
    configureMarkdownI18n,
} from "./markdown.js?v=site-public-6";

let pendingScrollFrameId = 0;
let messageT = (key) => key;

export function configureMessageI18n(options = {}) {
    if (typeof options.t === "function") {
        messageT = options.t;
        configureMarkdownI18n({ t: options.t });
    }
}

export function refreshMessagesLocalizedText() {
    if (!DOM.messages) {
        return;
    }

    DOM.messages.querySelectorAll("[data-message-aria-label-key]").forEach((message) => {
        message.setAttribute(
            "aria-label",
            messageT(message.dataset.messageAriaLabelKey),
        );
    });
    DOM.messages.querySelectorAll(".message-meta[data-label-key]").forEach((meta) => {
        meta.textContent = messageT(
            meta.dataset.labelKey,
            parseJsonDataset(meta.dataset.labelParams),
        );
    });
    DOM.messages.querySelectorAll("[data-image-preview='true']").forEach((button) => {
        const label = button.dataset.previewLabel || messageT("console.previewImage");
        button.title = label;
        button.setAttribute("aria-label", label);
    });
    DOM.messages.querySelectorAll(".message-image").forEach((image) => {
        if (!image.getAttribute("alt")) {
            image.alt = messageT("console.attachedImage");
        }
    });
    DOM.messages.querySelectorAll(".message-file-meta").forEach((meta) => {
        const downloadUrl = meta.dataset.downloadUrl || "";
        const sizeBytes = Number(meta.dataset.sizeBytes || 0);
        meta.textContent = buildFileAttachmentMeta(downloadUrl, sizeBytes);
    });
}

export function addMessage(kind, content, label, options = {}) {
    const messageId = `msg-${++messageState.counter}`;
    const container = document.createElement("article");
    container.className = `message message-${kind}`;
    container.dataset.messageId = messageId;
    container.dataset.messageKind = kind;
    container.setAttribute("role", kind === "system" ? "status" : "group");
    const ariaLabelKey = options.ariaLabelKey || defaultMessageAriaLabelKey(kind);
    if (ariaLabelKey) {
        container.dataset.messageAriaLabelKey = ariaLabelKey;
    }
    container.setAttribute("aria-label", resolveMessageAriaLabel(kind, label, options));
    if (kind === "system") {
        container.setAttribute("aria-live", "polite");
    }

    const body = document.createElement("div");
    body.className = "message-text";
    renderMessageBody(body, kind, content, options);

    container.appendChild(body);
    syncMessageMeta(container, label, options);
    DOM.messages.appendChild(container);
    scheduleMathTypesetting(body);
    scheduleMessagesScrollToBottom();
    return messageId;
}

export function addSystemMessage(text) {
    addMessage("system", text, messageT("console.systemLabel"), {
        labelKey: "console.systemLabel",
        ariaLabelKey: "console.systemLabel",
    });
}

export function updateMessage(messageId, content, label, options = {}) {
    const container = DOM.messages.querySelector(`[data-message-id="${messageId}"]`);
    if (!container) {
        return;
    }

    const body = container.querySelector(".message-text");
    const kind = container.dataset.messageKind || "assistant";
    const ariaLabelKey = options.ariaLabelKey || defaultMessageAriaLabelKey(kind);
    if (ariaLabelKey) {
        container.dataset.messageAriaLabelKey = ariaLabelKey;
    }
    container.setAttribute("aria-label", resolveMessageAriaLabel(kind, label, options));
    syncMessageMeta(container, label, options);
    if (body) {
        renderMessageBody(body, kind, content, options);
        scheduleMathTypesetting(body);
    }
    scheduleMessagesScrollToBottom();
}

export function clearMessages() {
    clearMathTypesetting(DOM.messages);
    DOM.messages.innerHTML = "";
    messageState.counter = 0;
}

export function scheduleMessagesScrollToBottom() {
    if (!DOM.messages || pendingScrollFrameId) {
        return;
    }

    pendingScrollFrameId = window.requestAnimationFrame(() => {
        pendingScrollFrameId = 0;
        scrollMessagesToBottom();
    });
}

export function removeMessage(messageId) {
    const container = DOM.messages.querySelector(`[data-message-id="${messageId}"]`);
    if (!container) {
        return;
    }
    clearMathTypesetting(container);
    container.remove();
}

export function initializeMessageInteractions() {
    if (DOM.messages) {
        DOM.messages.addEventListener("click", handleMessageAreaClick);
    }
    if (DOM.messageImageDialogClose) {
        DOM.messageImageDialogClose.addEventListener("click", closeMessageImagePreview);
    }
    if (DOM.messageImageDialog) {
        DOM.messageImageDialog.addEventListener("click", handleMessageImageDialogClick);
        DOM.messageImageDialog.addEventListener("close", resetMessageImagePreview);
        DOM.messageImageDialog.addEventListener("cancel", () => {
            resetMessageImagePreview();
        });
    }
}

function syncMessageMeta(container, label, options = {}) {
    const existingMeta = container.querySelector(".message-meta");
    const body = container.querySelector(".message-text");

    if (!options.showMeta) {
        if (existingMeta) {
            existingMeta.remove();
        }
        return;
    }

    const meta = existingMeta || document.createElement("div");
    meta.className = "message-meta";
    if (options.labelKey) {
        meta.dataset.labelKey = options.labelKey;
        meta.dataset.labelParams = JSON.stringify(options.labelParams || {});
        meta.textContent = messageT(options.labelKey, options.labelParams || {});
    } else {
        delete meta.dataset.labelKey;
        delete meta.dataset.labelParams;
        meta.textContent = String(label || "");
    }

    if (!existingMeta) {
        if (body) {
            container.insertBefore(meta, body);
        } else {
            container.appendChild(meta);
        }
    }
}

function scrollMessagesToBottom() {
    if (!DOM.messages) {
        return;
    }

    DOM.messages.scrollTop = DOM.messages.scrollHeight;
}

function resolveMessageAriaLabel(kind, label, options = {}) {
    if (options.ariaLabelKey) {
        return messageT(options.ariaLabelKey, options.ariaLabelParams || {});
    }
    const customLabel = String(label || "").trim();
    if (customLabel) {
        return customLabel;
    }

    return messageT(defaultMessageAriaLabelKey(kind));
}

function defaultMessageAriaLabelKey(kind) {
    if (kind === "user") {
        return "console.youMessageAria";
    }
    if (kind === "assistant") {
        return "console.echoReplyAria";
    }
    if (kind === "system") {
        return "console.systemLabel";
    }
    return "console.messageAria";
}

function parseJsonDataset(value) {
    try {
        const parsed = JSON.parse(String(value || "{}"));
        return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_error) {
        return {};
    }
}

function renderMessageBody(element, kind, content, options = {}) {
    clearMathTypesetting(element);
    const normalizedContent = normalizeMessageContent(content);
    if (Array.isArray(normalizedContent)) {
        renderStructuredBody(element, kind, normalizedContent, options);
        return;
    }

    const renderMode = resolveMessageRenderMode(kind, options);
    if (renderMode === "markdown") {
        renderMarkdownBody(element, normalizedContent);
        return;
    }
    renderPlainTextBody(element, normalizedContent);
}

function resolveMessageRenderMode(kind, options) {
    if (options.renderMode === "markdown") {
        return "markdown";
    }
    if (options.renderMode === "plain") {
        return "plain";
    }
    return kind === "assistant" ? "markdown" : "plain";
}

function renderPlainTextBody(element, text) {
    element.className = "message-text message-text-plain";
    element.textContent = String(text || "");
}

function renderMarkdownBody(element, text) {
    element.className = "message-text message-text-markdown";
    element.replaceChildren(buildMarkdownFragment(String(text || "")));
}

function renderStructuredBody(element, kind, contentBlocks, options) {
    const renderMode = resolveMessageRenderMode(kind, options);
    const fragment = document.createDocumentFragment();

    contentBlocks.forEach((block) => {
        const blockType = String(block.type || "").trim();
        if (blockType === TEXT_CONTENT_BLOCK_TYPE) {
            fragment.appendChild(
                buildTextBlock(
                    String(block.text || ""),
                    renderMode,
                ),
            );
            return;
        }

        if (blockType === IMAGE_URL_CONTENT_BLOCK_TYPE) {
            const imageUrl = String(block.image_url?.url || "").trim();
            const previewUrl = String(block.image_url?.preview_url || "").trim();
            if (imageUrl) {
                fragment.appendChild(buildImageBlock(previewUrl || imageUrl));
            }
            return;
        }

        if (blockType === FILE_ATTACHMENT_CONTENT_BLOCK_TYPE) {
            fragment.appendChild(buildFileAttachmentBlock(block.file_attachment));
            return;
        }

        if (blockType) {
            fragment.appendChild(buildTextBlock(`[${blockType}]`, "plain"));
        }
    });

    element.className = "message-text message-text-structured";
    if (!fragment.childNodes.length) {
        element.textContent = "";
        return;
    }
    element.replaceChildren(fragment);
}

function buildTextBlock(text, renderMode) {
    const block = document.createElement("div");
    block.className = "message-block message-block-text";
    if (renderMode === "markdown") {
        block.classList.add("message-text-markdown");
        block.replaceChildren(buildMarkdownFragment(String(text || "")));
        return block;
    }

    block.classList.add("message-text-plain");
    block.textContent = String(text || "");
    return block;
}

function buildImageBlock(imageUrl) {
    const block = document.createElement("div");
    block.className = "message-block message-block-image";

    const previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "message-image-link";
    previewButton.dataset.imagePreview = "true";
    previewButton.dataset.imageUrl = imageUrl;
    previewButton.dataset.previewLabel = "";
    previewButton.title = messageT("console.previewImage");
    previewButton.setAttribute("aria-label", messageT("console.previewImage"));

    const image = document.createElement("img");
    image.className = "message-image";
    image.src = imageUrl;
    image.alt = messageT("console.attachedImage");
    image.loading = "lazy";

    previewButton.appendChild(image);
    block.appendChild(previewButton);
    return block;
}

function buildFileAttachmentBlock(fileAttachment) {
    const attachment = fileAttachment && typeof fileAttachment === "object"
        ? fileAttachment
        : {};
    const fileName = String(attachment.name || "").trim() || messageT("console.unnamedFile");
    const downloadUrl = String(attachment.download_url || "").trim();
    const sizeBytes = Number(attachment.size_bytes || 0);

    const block = document.createElement("div");
    block.className = "message-block message-block-file";

    const card = downloadUrl
        ? document.createElement("a")
        : document.createElement("div");
    card.className = "message-file-card";

    if (downloadUrl) {
        card.href = downloadUrl;
        card.target = "_blank";
        card.rel = "noreferrer";
        card.download = fileName;
    }

    const body = document.createElement("div");
    body.className = "message-file-body";

    const name = document.createElement("div");
    name.className = "message-file-name";
    name.textContent = fileName;
    body.appendChild(name);

    const meta = document.createElement("div");
    meta.className = "message-file-meta";
    meta.dataset.downloadUrl = downloadUrl;
    meta.dataset.sizeBytes = String(sizeBytes || 0);
    meta.textContent = buildFileAttachmentMeta(downloadUrl, sizeBytes);
    if (meta.textContent) {
        body.appendChild(meta);
    }

    card.appendChild(body);
    block.appendChild(card);
    return block;
}

function buildFileAttachmentMeta(downloadUrl, sizeBytes) {
    const parts = [];
    if (downloadUrl) {
        parts.push(messageT("console.clickDownload"));
    } else {
        parts.push(messageT("console.uploaded"));
    }

    const sizeText = formatFileSize(sizeBytes);
    if (sizeText) {
        parts.push(sizeText);
    }
    return parts.join(" · ");
}

function formatFileSize(sizeBytes) {
    const size = Number(sizeBytes || 0);
    if (!Number.isFinite(size) || size <= 0) {
        return "";
    }
    if (size < 1024) {
        return `${size} B`;
    }
    if (size < 1024 * 1024) {
        return `${(size / 1024).toFixed(1).replace(/\\.0$/, "")} KB`;
    }
    return `${(size / (1024 * 1024)).toFixed(1).replace(/\\.0$/, "")} MB`;
}

function handleMessageAreaClick(event) {
    const previewTrigger = event.target.closest(".message-image-link[data-image-preview='true']");
    if (!previewTrigger || !DOM.messageImageDialog) {
        return;
    }

    const imageUrl = String(previewTrigger.dataset.imageUrl || "").trim();
    if (!imageUrl) {
        return;
    }

    openMessageImagePreview(imageUrl);
}

function openMessageImagePreview(imageUrl) {
    if (!DOM.messageImageDialog || !DOM.messageImageDialogImage) {
        return;
    }

    DOM.messageImageDialogImage.src = imageUrl;

    if (!DOM.messageImageDialog.open) {
        DOM.messageImageDialog.showModal();
    }
}

function closeMessageImagePreview() {
    if (DOM.messageImageDialog?.open) {
        DOM.messageImageDialog.close();
    }
}

function handleMessageImageDialogClick(event) {
    if (event.target === DOM.messageImageDialog) {
        closeMessageImagePreview();
    }
}

function resetMessageImagePreview() {
    if (DOM.messageImageDialogImage) {
        DOM.messageImageDialogImage.removeAttribute("src");
    }
}

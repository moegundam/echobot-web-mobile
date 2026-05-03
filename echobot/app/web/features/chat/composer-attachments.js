import { DOM } from "../../core/dom.js";
import { chatState } from "../../core/store.js";

const MAX_COMPOSER_IMAGES = 20;
const MAX_COMPOSER_FILES = 20;
const IMAGE_FILE_NAME_PATTERN = /\.(avif|bmp|gif|heic|heif|ico|jpe?g|png|tiff?|webp)$/i;
let composerT = (key) => key;

export function createComposerAttachmentsController(deps) {
    const {
        deleteAttachment,
        setRunStatus,
        t = (key) => key,
        uploadChatFile,
        uploadChatImage,
    } = deps;
    composerT = t;
    let fileDragDepth = 0;
    let fileDropUploadInFlight = false;

    function handleComposerFileButtonClick() {
        if (!DOM.composerFileInput || isComposerLocked()) {
            return;
        }

        DOM.composerFileInput.click();
    }

    async function handleComposerFileInputChange() {
        if (!DOM.composerFileInput) {
            return;
        }

        const selectedFiles = Array.from(DOM.composerFileInput.files || []);
        DOM.composerFileInput.value = "";
        if (!selectedFiles.length) {
            return;
        }

        try {
            const result = await addComposerFiles(selectedFiles);
            if (result.truncated) {
                setRunStatus(result.limitMessage);
            }
        } catch (error) {
            console.error("Failed to load composer files", error);
            setRunStatus(error.message || t("console.fileUploadFailed"));
        }
    }

    async function handleComposerFilesClick(event) {
        const removeButton = event.target.closest("[data-composer-file-id]");
        if (!removeButton) {
            return;
        }

        const fileId = String(removeButton.dataset.composerFileId || "").trim();
        if (!fileId) {
            return;
        }

        const existingFiles = chatState.composerFiles || [];
        const removedFile = existingFiles.find((file) => file.id === fileId) || null;
        chatState.composerFiles = existingFiles.filter((file) => file.id !== fileId);
        renderComposerFiles();
        if (removedFile && removedFile.attachmentId) {
            try {
                await deleteAttachment(removedFile.attachmentId);
            } catch (error) {
                console.error("Failed to delete removed composer file", error);
                setRunStatus(error.message || t("console.fileCleanupFailed"));
            }
        }
    }

    function handleComposerImageButtonClick() {
        if (!DOM.composerImageInput || isComposerLocked()) {
            return;
        }

        DOM.composerImageInput.click();
    }

    async function handleComposerImageInputChange() {
        if (!DOM.composerImageInput) {
            return;
        }

        const selectedFiles = Array.from(DOM.composerImageInput.files || []);
        DOM.composerImageInput.value = "";
        if (!selectedFiles.length) {
            return;
        }

        try {
            const result = await addComposerImages(selectedFiles);
            if (result.truncated) {
                setRunStatus(result.limitMessage);
            }
        } catch (error) {
            console.error("Failed to load composer images", error);
            setRunStatus(error.message || t("console.imageUploadFailed"));
        }
    }

    async function handlePromptPaste(event) {
        if (!DOM.promptInput || isComposerLocked()) {
            return;
        }

        const pastedFiles = extractTransferFiles(event.clipboardData);
        if (!pastedFiles.length) {
            return;
        }

        event.preventDefault();

        const statusText = await importComposerTransfers(pastedFiles, {
            actionLabel: t("console.pasted"),
            imageLogLabel: "Failed to upload pasted images",
            fileLogLabel: "Failed to upload pasted files",
        });
        if (statusText) {
            setRunStatus(statusText);
        }
    }

    async function handleComposerImagesClick(event) {
        const removeButton = event.target.closest("[data-composer-image-id]");
        if (!removeButton) {
            return;
        }

        const imageId = String(removeButton.dataset.composerImageId || "").trim();
        if (!imageId) {
            return;
        }

        const existingImages = chatState.composerImages || [];
        const removedImage = existingImages.find((image) => image.id === imageId) || null;
        chatState.composerImages = existingImages.filter((image) => image.id !== imageId);
        renderComposerImages();
        if (removedImage && removedImage.attachmentId) {
            try {
                await deleteAttachment(removedImage.attachmentId);
            } catch (error) {
                console.error("Failed to delete removed composer image", error);
                setRunStatus(error.message || t("console.imageCleanupFailed"));
            }
        }
    }

    function handleWindowFileDragEnter(event) {
        if (!isFileTransferEvent(event)) {
            return;
        }

        event.preventDefault();
        fileDragDepth += 1;
        syncWindowFileDropOverlay();
    }

    function handleWindowFileDragOver(event) {
        if (!isFileTransferEvent(event)) {
            return;
        }

        event.preventDefault();
        if (event.dataTransfer) {
            event.dataTransfer.dropEffect = canAcceptFileDrop() ? "copy" : "none";
        }
        syncWindowFileDropOverlay();
    }

    function handleWindowFileDragLeave(event) {
        if (!isFileTransferEvent(event)) {
            return;
        }

        fileDragDepth = Math.max(fileDragDepth - 1, 0);
        if (fileDragDepth === 0 || !isViewportPoint(event.clientX, event.clientY)) {
            resetWindowFileDropState();
            return;
        }

        syncWindowFileDropOverlay();
    }

    async function handleWindowFileDrop(event) {
        if (!isFileTransferEvent(event)) {
            return;
        }

        event.preventDefault();
        const droppedFiles = extractTransferFiles(event.dataTransfer);
        resetWindowFileDropState();
        if (!droppedFiles.length) {
            return;
        }

        if (fileDropUploadInFlight) {
            setRunStatus(t("console.processingDroppedAttachments"));
            return;
        }
        if (isComposerLocked()) {
            setRunStatus(t("console.dragUploadBlockedBusy"));
            return;
        }

        fileDropUploadInFlight = true;
        try {
            const statusText = await importComposerTransfers(droppedFiles, {
                actionLabel: t("console.dropped"),
                imageLogLabel: "Failed to upload dropped images",
                fileLogLabel: "Failed to upload dropped files",
            });
            if (statusText) {
                setRunStatus(statusText);
            }
        } finally {
            fileDropUploadInFlight = false;
            syncWindowFileDropOverlay();
        }
    }

    function refreshComposerAttachments() {
        renderComposerFiles();
        renderComposerImages();
        syncWindowFileDropOverlay();
    }

    function clearComposerAttachments() {
        chatState.composerImages = [];
        chatState.composerFiles = [];
        renderComposerFiles();
        renderComposerImages();
        resetWindowFileDropState();
    }

    async function addComposerFiles(selectedFiles) {
        const files = Array.isArray(selectedFiles) ? selectedFiles : [];
        const limitMessage = t("console.maxFiles", { count: MAX_COMPOSER_FILES });
        if (!files.length) {
            return {
                addedCount: 0,
                truncated: false,
                limitMessage,
            };
        }

        const existingFiles = chatState.composerFiles || [];
        const availableSlots = Math.max(MAX_COMPOSER_FILES - existingFiles.length, 0);
        if (availableSlots <= 0) {
            return {
                addedCount: 0,
                truncated: true,
                limitMessage,
            };
        }

        const filesToUpload = files.slice(0, availableSlots);
        const nextFiles = await readComposerFiles(filesToUpload, uploadChatFile, deleteAttachment);
        if (nextFiles.length) {
            chatState.composerFiles = [...existingFiles, ...nextFiles];
            renderComposerFiles();
        }

        return {
            addedCount: nextFiles.length,
            truncated: filesToUpload.length < files.length,
            limitMessage,
        };
    }

    async function addComposerImages(selectedFiles) {
        const files = Array.isArray(selectedFiles) ? selectedFiles : [];
        const limitMessage = t("console.maxImages", { count: MAX_COMPOSER_IMAGES });
        if (!files.length) {
            return {
                addedCount: 0,
                truncated: false,
                limitMessage,
            };
        }

        const existingImages = chatState.composerImages || [];
        const availableSlots = Math.max(MAX_COMPOSER_IMAGES - existingImages.length, 0);
        if (availableSlots <= 0) {
            return {
                addedCount: 0,
                truncated: true,
                limitMessage,
            };
        }

        const imagesToUpload = files.slice(0, availableSlots);
        const nextImages = await readComposerImages(imagesToUpload, uploadChatImage, deleteAttachment);
        if (nextImages.length) {
            chatState.composerImages = [...existingImages, ...nextImages];
            renderComposerImages();
        }

        return {
            addedCount: nextImages.length,
            truncated: imagesToUpload.length < files.length,
            limitMessage,
        };
    }

    async function importComposerTransfers(
        files,
        {
            actionLabel,
            imageLogLabel,
            fileLogLabel,
        },
    ) {
        const imageFiles = files.filter((file) => isImageFile(file));
        const otherFiles = files.filter((file) => !isImageFile(file));
        const uploadErrors = [];
        let uploadedImageCount = 0;
        let uploadedFileCount = 0;
        let imageLimitReached = false;
        let fileLimitReached = false;

        if (imageFiles.length) {
            try {
                const result = await addComposerImages(imageFiles);
                uploadedImageCount = result.addedCount;
                imageLimitReached = result.truncated;
            } catch (error) {
                console.error(imageLogLabel, error);
                uploadErrors.push(error.message || t("console.imageUploadFailed"));
            }
        }

        if (otherFiles.length) {
            try {
                const result = await addComposerFiles(otherFiles);
                uploadedFileCount = result.addedCount;
                fileLimitReached = result.truncated;
            } catch (error) {
                console.error(fileLogLabel, error);
                uploadErrors.push(error.message || t("console.fileUploadFailed"));
            }
        }

        return buildAttachmentTransferStatus({
            actionLabel,
            uploadedImageCount,
            uploadedFileCount,
            imageLimitReached,
            fileLimitReached,
            uploadErrors,
        });
    }

    function isComposerLocked() {
        return chatState.chatBusy || Boolean(chatState.activeChatJobId);
    }

    function canAcceptFileDrop() {
        return !isComposerLocked() && !fileDropUploadInFlight;
    }

    function syncWindowFileDropOverlay() {
        if (!DOM.windowFileDropOverlay) {
            return;
        }

        DOM.windowFileDropOverlay.hidden = !(fileDragDepth > 0 && canAcceptFileDrop());
    }

    function resetWindowFileDropState() {
        fileDragDepth = 0;
        syncWindowFileDropOverlay();
    }

    return {
        clearComposerAttachments,
        handleComposerFileButtonClick,
        handleComposerFileInputChange,
        handleComposerFilesClick,
        handleComposerImageButtonClick,
        handleComposerImageInputChange,
        handleComposerImagesClick,
        handlePromptPaste,
        handleWindowFileDragEnter,
        handleWindowFileDragLeave,
        handleWindowFileDragOver,
        handleWindowFileDrop,
        refreshComposerAttachments,
    };
}

async function readComposerImages(files, uploadImage, deleteAttachment) {
    const imageFiles = files.filter((file) => isImageFile(file));
    const nextImages = [];
    try {
        for (let index = 0; index < imageFiles.length; index += 1) {
            const file = imageFiles[index];
            const uploaded = await uploadImage(file);
            nextImages.push({
                id: `img-${Date.now()}-${index}-${Math.random().toString(16).slice(2, 8)}`,
                name: uploaded.original_filename || file.name || "image",
                attachmentId: String(uploaded.attachment_id || "").trim(),
                url: String(uploaded.url || "").trim(),
                previewUrl: String(uploaded.preview_url || "").trim(),
            });
        }
    } catch (error) {
        await cleanupUploadedComposerEntries(nextImages, deleteAttachment);
        throw error;
    }

    return nextImages.filter(
        (image) => String(image.attachmentId || "").trim() && String(image.url || "").trim(),
    );
}

async function readComposerFiles(files, uploadFile, deleteAttachment) {
    const nextFiles = [];
    try {
        for (let index = 0; index < files.length; index += 1) {
            const file = files[index];
            const uploaded = await uploadFile(file);
            nextFiles.push({
                id: `file-${Date.now()}-${index}-${Math.random().toString(16).slice(2, 8)}`,
                name: uploaded.original_filename || file.name || "file",
                attachmentId: String(uploaded.attachment_id || "").trim(),
                downloadUrl: String(uploaded.download_url || "").trim(),
                contentType: String(uploaded.content_type || "").trim(),
                sizeBytes: Number(uploaded.size_bytes || file.size || 0),
                workspacePath: String(uploaded.workspace_path || "").trim(),
            });
        }
    } catch (error) {
        await cleanupUploadedComposerEntries(nextFiles, deleteAttachment);
        throw error;
    }

    return nextFiles.filter(
        (file) => String(file.attachmentId || "").trim() && String(file.workspacePath || "").trim(),
    );
}

async function cleanupUploadedComposerEntries(entries, deleteAttachment) {
    if (!Array.isArray(entries) || entries.length === 0) {
        return;
    }

    await Promise.allSettled(
        entries
            .map((entry) => String(entry?.attachmentId || "").trim())
            .filter(Boolean)
            .map((attachmentId) => deleteAttachment(attachmentId)),
    );
}

function extractTransferFiles(transfer) {
    if (!transfer) {
        return [];
    }

    const itemFiles = Array.from(transfer.items || [])
        .filter((item) => item?.kind === "file")
        .map((item) => item.getAsFile())
        .filter((file) => Boolean(file));
    if (itemFiles.length) {
        return itemFiles;
    }

    return Array.from(transfer.files || []).filter((file) => Boolean(file));
}

function isImageFile(file) {
    const contentType = String(file?.type || "").trim().toLowerCase();
    if (contentType.startsWith("image/")) {
        return true;
    }

    const fileName = String(file?.name || "").trim();
    return IMAGE_FILE_NAME_PATTERN.test(fileName);
}

function isFileTransferEvent(event) {
    const transfer = event?.dataTransfer;
    if (!transfer) {
        return false;
    }

    return Array.from(transfer.types || []).includes("Files");
}

function isViewportPoint(clientX, clientY) {
    return (
        Number.isFinite(clientX)
        && Number.isFinite(clientY)
        && clientX > 0
        && clientY > 0
        && clientX < window.innerWidth
        && clientY < window.innerHeight
    );
}

function buildAttachmentTransferStatus({
    actionLabel,
    uploadedImageCount,
    uploadedFileCount,
    imageLimitReached,
    fileLimitReached,
    uploadErrors,
}) {
    const statusParts = [];
    const uploadedParts = [];

    if (uploadedImageCount > 0) {
        uploadedParts.push(composerT("console.imageCount", { count: uploadedImageCount }));
    }
    if (uploadedFileCount > 0) {
        uploadedParts.push(composerT("console.fileCount", { count: uploadedFileCount }));
    }
    if (uploadedParts.length) {
        statusParts.push(`${actionLabel} ${uploadedParts.join(composerT("console.listSeparator"))}`);
    }

    if (imageLimitReached || fileLimitReached) {
        if (statusParts.length) {
            statusParts.push(composerT("console.attachmentLimitIgnored"));
        } else if (imageLimitReached && fileLimitReached) {
            statusParts.push(composerT("console.imageAndFileLimitsReached"));
        } else if (imageLimitReached) {
            statusParts.push(composerT("console.maxImages", { count: MAX_COMPOSER_IMAGES }));
        } else {
            statusParts.push(composerT("console.maxFiles", { count: MAX_COMPOSER_FILES }));
        }
    }

    if (uploadErrors.length) {
        statusParts.push(composerT("console.partialUploadFailed", { errors: uploadErrors.join("；") }));
    }

    return statusParts.join("，");
}

function renderComposerFiles() {
    if (!DOM.composerFiles) {
        return;
    }

    const composerFiles = Array.isArray(chatState.composerFiles)
        ? chatState.composerFiles
        : [];
    DOM.composerFiles.innerHTML = "";
    DOM.composerFiles.hidden = composerFiles.length === 0;

    composerFiles.forEach((file) => {
        const card = document.createElement("div");
        card.className = "composer-file-chip";

        const body = document.createElement("div");
        body.className = "composer-file-body";

        const name = document.createElement("div");
        name.className = "composer-file-name";
        name.textContent = file.name || composerT("console.unnamedFile");
        body.appendChild(name);

        const meta = document.createElement("div");
        meta.className = "composer-file-meta";
        meta.textContent = describeComposerFile(file);
        if (meta.textContent) {
            body.appendChild(meta);
        }

        card.appendChild(body);

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "composer-file-remove";
        removeButton.dataset.composerFileId = file.id;
        removeButton.textContent = composerT("console.remove");
        removeButton.title = composerT("console.removeFile");
        removeButton.setAttribute("aria-label", composerT("console.removeFile"));
        removeButton.disabled = chatState.chatBusy || Boolean(chatState.activeChatJobId);
        card.appendChild(removeButton);

        DOM.composerFiles.appendChild(card);
    });
}

function describeComposerFile(file) {
    const sizeText = formatComposerFileSize(file.sizeBytes);
    if (sizeText) {
        return `${composerT("console.pendingSend")} · ${sizeText}`;
    }

    return composerT("console.pendingSend");
}

function formatComposerFileSize(sizeBytes) {
    const size = Number(sizeBytes || 0);
    if (!Number.isFinite(size) || size <= 0) {
        return "";
    }
    if (size < 1024) {
        return `${size} B`;
    }
    if (size < 1024 * 1024) {
        return `${(size / 1024).toFixed(1).replace(/\.0$/, "")} KB`;
    }

    return `${(size / (1024 * 1024)).toFixed(1).replace(/\.0$/, "")} MB`;
}

function renderComposerImages() {
    if (!DOM.composerImages) {
        return;
    }

    const composerImages = Array.isArray(chatState.composerImages)
        ? chatState.composerImages
        : [];
    DOM.composerImages.innerHTML = "";
    DOM.composerImages.hidden = composerImages.length === 0;

    composerImages.forEach((image) => {
        const card = document.createElement("div");
        card.className = "composer-image-chip";

        const preview = document.createElement("img");
        preview.className = "composer-image-thumb";
        preview.src = image.previewUrl || image.url;
        preview.alt = image.name || composerT("console.selectedImage");
        preview.loading = "lazy";
        card.appendChild(preview);

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "composer-image-remove";
        removeButton.dataset.composerImageId = image.id;
        removeButton.textContent = "×";
        removeButton.title = composerT("console.removeImage");
        removeButton.setAttribute("aria-label", composerT("console.removeImage"));
        removeButton.disabled = chatState.chatBusy || Boolean(chatState.activeChatJobId);
        card.appendChild(removeButton);

        DOM.composerImages.appendChild(card);
    });
}

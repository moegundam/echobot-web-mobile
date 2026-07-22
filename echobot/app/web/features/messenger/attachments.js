export function createMessengerAttachmentController({
    fileInput,
    fileSummary,
    attachmentsElement,
    i18n,
    uploadChatFile,
    uploadChatImage,
    setStatus,
}) {
    async function uploadSelectedFiles(getAttachments, setAttachments) {
        if (!fileInput) {
            return;
        }
        const files = Array.from(fileInput.files || []);
        if (files.length === 0) {
            return;
        }

        setStatus("messenger.uploading");
        try {
            for (const file of files) {
                const nextAttachment = await uploadMessengerAttachment(file);
                setAttachments([...getAttachments(), nextAttachment]);
                renderPendingAttachments(getAttachments, setAttachments);
            }
            setStatus("messenger.attached");
        } catch (error) {
            console.error(error);
            setStatus("messenger.uploadFailed");
        } finally {
            fileInput.value = "";
            updateFileSelectionSummary();
        }
    }

    async function uploadMessengerAttachment(file) {
        const kind = String(file && file.type || "").startsWith("image/")
            ? "image"
            : "file";
        const payload = kind === "image"
            ? await uploadChatImage(file)
            : await uploadChatFile(file);
        const attachmentId = String((payload && payload.attachment_id) || "");
        if (!attachmentId) {
            throw new Error(i18n.t("messenger.uploadFailed"));
        }
        return {
            kind,
            attachment_id: attachmentId,
            label: String(
                (payload && payload.original_filename) || (file && file.name) || attachmentId,
            ),
        };
    }

    function updateFileSelectionSummary() {
        if (!fileSummary) {
            return;
        }
        const count = Array.from((fileInput && fileInput.files) || []).length;
        const key = count > 0 ? "messenger.filesSelected" : "messenger.noFilesSelected";
        fileSummary.dataset.i18nKey = key;
        fileSummary.textContent = i18n.t(key, { count });
    }

    function renderPendingAttachments(getAttachments, setAttachments) {
        if (!attachmentsElement) {
            return;
        }
        const chips = getAttachments().map((item, index) => {
            const chip = document.createElement("span");
            chip.className = "messenger-attachment-chip";
            const label = document.createElement("span");
            label.textContent = `${i18n.t("messenger.attached")}: ${item.label}`;
            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.textContent = i18n.t("messenger.removeAttachment");
            removeButton.addEventListener("click", () => {
                setAttachments(getAttachments().filter((_item, itemIndex) => itemIndex !== index));
                renderPendingAttachments(getAttachments, setAttachments);
            });
            chip.append(label, removeButton);
            return chip;
        });
        attachmentsElement.replaceChildren(...chips);
    }

    return {
        renderPendingAttachments,
        updateFileSelectionSummary,
        uploadMessengerAttachment,
        uploadSelectedFiles,
    };
}

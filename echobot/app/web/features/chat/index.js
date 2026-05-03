import { createComposerAttachmentsController } from "./composer-attachments.js?v=site-public-6";
import { createChatRunner } from "./job-runner.js?v=site-public-6";

export function createChatModule(deps) {
    const composer = createComposerAttachmentsController(deps);
    const runner = createChatRunner({
        ...deps,
        clearComposerAttachments: composer.clearComposerAttachments,
    });

    return {
        ...composer,
        ...runner,
        refreshLocalizedText: composer.refreshComposerAttachments,
    };
}

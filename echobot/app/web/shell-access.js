import { applyAccessContext } from "./features/access.js";
import { requestErrorMessage, requestJson } from "./modules/api.js";

const DEFAULT_ACCESS = Object.freeze({
    role: "user",
    can_access_console: false,
    can_manage_admin: false,
    can_use_agent: false,
});

export async function initShellAccessContext({
    t = (key) => key,
    onResolved = null,
} = {}) {
    applyAccessContext({ access: DEFAULT_ACCESS }, t);
    let access = DEFAULT_ACCESS;
    try {
        access = applyAccessContext(
            { access: await requestJson("/api/access") },
            t,
        );
    } catch (error) {
        console.warn(requestErrorMessage(error, t, "errors.accessLoadFailed"));
    }
    if (typeof onResolved === "function") {
        onResolved(access);
    }
    return access;
}

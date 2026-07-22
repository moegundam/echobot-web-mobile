export function availableSessionNames(...collections) {
    const names = [];
    const seen = new Set();
    for (const collection of collections) {
        for (const value of Array.isArray(collection) ? collection : []) {
            const name = String(value || "").trim();
            if (!name || seen.has(name)) {
                continue;
            }
            seen.add(name);
            names.push(name);
        }
    }
    return names;
}

export function resolveAvailableSessionName(requestedSessionName, sessionNames) {
    const availableNames = availableSessionNames(sessionNames);
    const requestedName = String(requestedSessionName || "").trim();
    if (requestedName && availableNames.includes(requestedName)) {
        return requestedName;
    }
    return availableNames[0] || "";
}

const THEME_STORAGE_KEY = "post_reader_theme";

let sessionCache = null;

async function apiRequest(path, options = {}) {
    const requestOptions = {
        method: options.method || "GET",
        credentials: "same-origin",
        headers: {
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {}),
        },
    };

    if (Object.prototype.hasOwnProperty.call(options, "body")) {
        requestOptions.body = typeof options.body === "string"
            ? options.body
            : JSON.stringify(options.body);
    }

    const response = await fetch(path, requestOptions);
    const contentType = response.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const payload = isJson ? await response.json() : null;

    if (!response.ok) {
        const error = new Error(payload?.message || `请求失败：HTTP ${response.status}`);
        error.status = response.status;
        error.payload = payload;
        throw error;
    }

    return payload;
}

async function getSession(force = false) {
    if (sessionCache && !force) {
        return sessionCache;
    }

    const session = await apiRequest("/api/session");
    sessionCache = session;
    return session;
}

async function login(username, password) {
    const session = await apiRequest("/api/login", {
        method: "POST",
        body: {
            username: String(username || "").trim(),
            password: String(password || ""),
        },
    });
    sessionCache = session;
    return session;
}

async function register(username, password, inviteCode) {
    const session = await apiRequest("/api/register", {
        method: "POST",
        body: {
            username: String(username || "").trim(),
            password: String(password || ""),
            invite_code: String(inviteCode || ""),
        },
    });
    sessionCache = session;
    return session;
}

async function logout(redirectPath = "./index.html") {
    try {
        await apiRequest("/api/logout", { method: "POST" });
    } catch {
        // Ignore logout failures and clear client state anyway.
    } finally {
        sessionCache = { authenticated: false, username: "" };
        window.location.href = redirectPath;
    }
}

async function requireAuth() {
    const session = await getSession(true);
    if (!session?.authenticated) {
        window.location.href = "./index.html";
        return null;
    }
    return session;
}

window.ThreadReaderAuth = {
    THEME_STORAGE_KEY,
    apiRequest,
    getSession,
    login,
    register,
    logout,
    requireAuth,
};

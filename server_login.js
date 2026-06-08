const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const loginUsernameInput = document.getElementById("usernameInput");
const loginPasswordInput = document.getElementById("passwordInput");
const registerUsernameInput = document.getElementById("registerUsernameInput");
const registerPasswordInput = document.getElementById("registerPasswordInput");
const registerPasswordConfirmInput = document.getElementById("registerPasswordConfirmInput");
const registerInviteCodeInput = document.getElementById("registerInviteCodeInput");
const authMessage = document.getElementById("authMessage");
const modeButtons = Array.from(document.querySelectorAll("[data-auth-mode]"));
const loginSubmitButton = loginForm.querySelector('button[type="submit"]');
const registerSubmitButton = registerForm.querySelector('button[type="submit"]');

let currentMode = "login";

initializeLoginPage();

async function initializeLoginPage() {
    try {
        const session = await window.ThreadReaderAuth.getSession(true);
        if (session?.authenticated) {
            window.location.replace("./server_home.html");
            return;
        }
    } catch (error) {
        setMessage(error.message || "无法检查登录状态。");
    }

    modeButtons.forEach((button) => {
        button.addEventListener("click", () => setMode(button.dataset.authMode || "login"));
    });
    loginForm.addEventListener("submit", handleLoginSubmit);
    registerForm.addEventListener("submit", handleRegisterSubmit);
    setMode(currentMode);
}

function setMode(mode) {
    currentMode = mode === "register" ? "register" : "login";
    const loginActive = currentMode === "login";

    loginForm.classList.toggle("portal-hidden", !loginActive);
    registerForm.classList.toggle("portal-hidden", loginActive);

    modeButtons.forEach((button) => {
        const active = button.dataset.authMode === currentMode;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
    });

    clearMessage();
}

function setMessage(text) {
    authMessage.textContent = String(text || "");
}

function clearMessage() {
    setMessage("");
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    clearMessage();
    loginSubmitButton.disabled = true;

    try {
        await window.ThreadReaderAuth.login(
            loginUsernameInput.value,
            loginPasswordInput.value,
        );
        window.location.href = "./server_home.html";
    } catch (error) {
        setMessage(error.message || "登录失败。");
        loginPasswordInput.select();
    } finally {
        loginSubmitButton.disabled = false;
    }
}

async function handleRegisterSubmit(event) {
    event.preventDefault();
    clearMessage();

    const password = String(registerPasswordInput.value || "");
    const passwordConfirm = String(registerPasswordConfirmInput.value || "");
    if (password !== passwordConfirm) {
        setMessage("两次输入的密码不一致。");
        registerPasswordConfirmInput.select();
        return;
    }

    registerSubmitButton.disabled = true;
    try {
        await window.ThreadReaderAuth.register(
            registerUsernameInput.value,
            password,
            registerInviteCodeInput.value,
        );
        window.location.href = "./server_home.html";
    } catch (error) {
        setMessage(error.message || "注册失败。");
        registerInviteCodeInput.select();
    } finally {
        registerSubmitButton.disabled = false;
    }
}

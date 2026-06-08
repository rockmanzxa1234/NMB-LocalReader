import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = CURRENT_DIR.parent

for candidate in ("", str(WORKSPACE_DIR)):
    while candidate in sys.path:
        sys.path.remove(candidate)

LOGIN_URL = "https://aweidao1.com/user/login"
BROWSER_MODE = "edge"
STORAGE_STATE_PATH = CURRENT_DIR / "awd_storage_state.json"
WAIT_MS = 8000


def launch_browser(playwright):
    mode = str(BROWSER_MODE).strip().lower()
    if mode == "playwright":
        return playwright.chromium.launch(headless=False, args=["--start-maximized"])
    if mode == "edge":
        return playwright.chromium.launch(
            channel="msedge",
            headless=False,
            args=["--start-maximized"],
        )
    raise ValueError("BROWSER_MODE 只支持 'playwright' 或 'edge'。")


def close_announcement_if_present(page):
    try:
        button = page.get_by_role("button", name="关闭")
        if button.count() > 0:
            button.first.click(timeout=3000)
            page.wait_for_timeout(500)
            return True
    except Exception:
        pass
    return False


def has_login_form(page):
    selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[autocomplete='current-password']",
        "input[type='text']",
        "input[name='username']",
        "input[autocomplete='username']",
    ]
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


def ensure_login_form(page):
    page.wait_for_timeout(WAIT_MS)
    close_announcement_if_present(page)

    if has_login_form(page):
        return

    candidates = [
        ("role-link", lambda: page.get_by_role("link", name="登录").first),
        ("role-button", lambda: page.get_by_role("button", name="登录").first),
        ("href-login", lambda: page.locator("a[href='/user/login']").first),
    ]

    for _, factory in candidates:
        try:
            locator = factory()
            if locator.count() == 0:
                continue
            locator.click(timeout=5000)
            page.wait_for_timeout(3000)
            close_announcement_if_present(page)
            if has_login_form(page):
                reveal_login_form(page)
                return
        except Exception:
            continue

    reveal_login_form(page)


def reveal_login_form(page):
    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass

    selectors = [
        "input[autocomplete='username']",
        "input[name='username']",
        "input[type='text']",
        "input[type='tel']",
        "input[autocomplete='current-password']",
        "input[type='password']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            locator.scroll_into_view_if_needed(timeout=3000)
            locator.click(timeout=3000)
            return
        except Exception:
            continue


def print_debug_summary(page):
    try:
        title = page.title()
    except Exception:
        title = ""

    try:
        text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        text = ""

    text = " ".join(text.split())
    print(f"页面标题: {title}")
    print(f"当前地址: {page.url}")
    print("页面文本摘录:")
    print(text[:500])


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "未安装 playwright。\n"
            "先执行:\n"
            "  pip install playwright\n"
            "\n"
            "如果 BROWSER_MODE = 'playwright'，还需要执行:\n"
            "  playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = launch_browser(p)
        context = browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        )
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        ensure_login_form(page)
        print_debug_summary(page)

        print("浏览器已打开登录页。")
        print("请在打开的页面里完成登录。")
        print("登录完成后，回到这里按回车保存登录态。")
        input()

        context.storage_state(path=str(STORAGE_STATE_PATH))
        print(f"已保存登录态: {STORAGE_STATE_PATH}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()

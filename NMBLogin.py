import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = CURRENT_DIR.parent

for candidate in ("", str(WORKSPACE_DIR)):
    while candidate in sys.path:
        sys.path.remove(candidate)

LOGIN_URL = "https://www.nmbxd1.com/Member/User/Index/login.html"
CONTENT_VERIFY_URL = "https://www.nmbxd1.com/t/50060847"
BROWSER_MODE = "edge"
STORAGE_STATE_PATH = CURRENT_DIR / "nmb_storage_state.json"


def launch_browser(playwright):
    mode = str(BROWSER_MODE).strip().lower()
    if mode == "playwright":
        return playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
    if mode == "edge":
        return playwright.chromium.launch(
            channel="msedge",
            headless=False,
            args=["--start-maximized"],
        )
    raise ValueError("BROWSER_MODE 只支持 'playwright' 或 'edge'。")


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


def print_cookie_summary(context, url):
    try:
        cookies = context.cookies(url)
    except Exception:
        cookies = []

    print(f"目标站点 cookie 数量: {len(cookies)}")
    for cookie in cookies:
        name = str(cookie.get("name") or "").strip()
        domain = str(cookie.get("domain") or "").strip()
        if name:
            print(f"  {name} @ {domain}")


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
        page.wait_for_timeout(3000)
        print_debug_summary(page)

        print("浏览器已打开 NMB 登录页。")
        print("请在浏览器里手动完成这条流程：")
        print("1. 登录")
        print("2. 进入“饼干”")
        print(f"3. 再手动打开一个内容页，例如：{CONTENT_VERIFY_URL}")
        print("4. 确认当前页面已经停在内容页")
        print("完成后回到这里按回车，脚本只保存当前浏览器状态，不再强制跳转。")
        input()

        page.wait_for_timeout(1000)
        print_debug_summary(page)
        print_cookie_summary(context, CONTENT_VERIFY_URL)

        context.storage_state(path=str(STORAGE_STATE_PATH))
        print(f"已保存登录态: {STORAGE_STATE_PATH}")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()

import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

from downloader_common import *
CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = CURRENT_DIR.parent

for candidate in ("", str(WORKSPACE_DIR)):
    while candidate in sys.path:
        sys.path.remove(candidate)

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

ROOT = CURRENT_DIR
ORIGINAL_PAGE_FOLDER_NAME = "original_pages"
ORIGINAL_PAGES_ROOT = ROOT / ORIGINAL_PAGE_FOLDER_NAME
THREAD_META_FILENAME = "thread_meta.json"
CONCATE_PENDING_FILENAME = "concate_pending.json"
STORAGE_STATE_PATH = ROOT / "awd_storage_state.json"

THREAD_URL = "https://aweidao1.com/t/xxxx"
THREAD_TITLE = ""
TAGS = []
SERIES = ""
INSTALLMENT = None
GENRE = ""
STATUS = ""

BROWSER_MODE = "edge"
WAIT_MS = 1500
PAGE_TIMEOUT_MS = 60000

HEADERS = {
    "cookie": "",
    "referer": THREAD_URL,
    "upgrade-insecure-requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

SESSION = create_session(HEADERS)

TIME_TEXT_RE = re.compile(r"^\s*(?:刚刚|\d+\s*(?:秒|分钟|小时|天|周|个月|月|年)前)\s*$")
POST_NO_RE = re.compile(r"No\.(\d+)", re.IGNORECASE)
QUOTE_POST_NO_RE = re.compile(r">>\s*NO\.(\d+)", re.IGNORECASE)
REPLY_LINK_RE = re.compile(r"/t/\d+\?r=\d+")
RELATIVE_TIME_RE = re.compile(r"^\s*(\d+)\s*(秒|分钟|小时|天|周|个月|月|年)前\s*$")


def extract_thread_id(thread_url):
    parts = urlparse(str(thread_url)).path.strip("/").split("/")
    if parts and parts[-2:-1] == ["t"]:
        return parts[-1]
    if parts and parts[0] == "t":
        return parts[-1]
    raise ValueError(f"无法从链接解析串号: {thread_url}")

def launch_browser(playwright):
    mode = str(BROWSER_MODE).strip().lower()
    if mode == "playwright":
        return playwright.chromium.launch(headless=True)
    if mode == "edge":
        try:
            return playwright.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:
            raise RuntimeError(
                "启动本机 Edge 失败。\n"
                "请确认系统已安装 Microsoft Edge，或者把 BROWSER_MODE 改回 'playwright'。"
            ) from exc
    raise ValueError("BROWSER_MODE 只支持 'playwright' 或 'edge'。")

def close_announcement_if_present(page):
    try:
        button = page.get_by_role("button", name="关闭")
        if button.count() > 0:
            button.first.click(timeout=2000)
            page.wait_for_timeout(300)
    except Exception:
        pass


def wait_for_thread_ready(page, thread_id, expected_page_no=None):
    page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    page.wait_for_function(
        """
        ({ threadId }) => {
          const text = document.body ? document.body.innerText : "";
          return text.includes(`No.${threadId}`);
        }
        """,
        arg={"threadId": str(thread_id)},
        timeout=PAGE_TIMEOUT_MS,
    )

    close_announcement_if_present(page)

    if expected_page_no is not None:
        try:
            page.wait_for_function(
                """
                ({ pageNo }) => {
                  const current = document.querySelector(
                    "nav[aria-label='pagination navigation'] button[aria-current='true']"
                  );
                  if (!current) {
                    return pageNo === 1;
                  }
                  return current.textContent.trim() === String(pageNo);
                }
                """,
                arg={"pageNo": int(expected_page_no)},
                timeout=15000,
            )
        except Exception:
            pass

    page.wait_for_timeout(WAIT_MS)


def build_page_candidate_urls(thread_url, page_no):
    if page_no <= 1:
        return [thread_url]

    separator = "&" if "?" in thread_url else "?"
    return [f"{thread_url}{separator}page={page_no}"]


def is_post_card_content(tag):
    if tag.name != "div":
        return False

    classes = tag.get("class") or []
    if "MuiCardContent-root" not in classes:
        return False

    card_id = str(tag.get("id") or "").strip()
    return card_id.isdigit()


def is_card_root(tag):
    if tag.name != "div":
        return False
    classes = tag.get("class") or []
    return "MuiCard-root" in classes


def normalize_quote_text(text):
    return QUOTE_POST_NO_RE.sub(lambda match: f">>No.{match.group(1)}", text)

def is_likely_user_text(text):
    value = str(text or "").strip()
    if not value:
        return False
    if value == "选择饼干":
        return False
    if normalize_po_marker(value):
        return False
    if TIME_TEXT_RE.match(value):
        return False
    if POST_NO_RE.search(value):
        return False
    if len(value) > 40:
        return False
    return True


def collect_header_like_texts(container):
    if container is None:
        return []

    candidates = []
    seen = set()
    for tag in container.find_all(["p", "div", "span", "a", "button"]):
        text = tag.get_text(" ", strip=True)
        if not is_likely_user_text(text):
            continue

        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append((tag, text))
    return candidates


def clean_multiline_text(text):
    lines = [line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_post_content(content_block):
    if content_block is None:
        return ""

    pieces = []
    font_nodes = content_block.find_all("font")
    if font_nodes:
        for font_node in font_nodes:
            text = clean_multiline_text(
                extract_text_with_inline_tags(
                    font_node,
                    normalize_crlf=True,
                    max_consecutive_newlines=2,
                )
            )
            text = normalize_quote_text(text)
            if text:
                pieces.append(text)
    else:
        clone = BeautifulSoup(str(content_block), "html.parser")
        for link in clone.find_all("a", href=REPLY_LINK_RE):
            ancestor = link
            while ancestor and ancestor.name != "div":
                ancestor = ancestor.parent
            if ancestor is not None:
                ancestor.decompose()
            else:
                link.decompose()
        text = clean_multiline_text(
            extract_text_with_inline_tags(
                clone,
                normalize_crlf=True,
                max_consecutive_newlines=2,
            )
        )
        text = normalize_quote_text(text)
        if text:
            pieces.append(text)

    if not pieces:
        return ""

    merged = "\n".join(piece for piece in pieces if piece)
    merged = re.sub(r"\n{3,}", "\n\n", merged)
    return merged.strip()


def extract_post_image_url(container, thread_url):
    if container is None:
        return ""

    for link in container.find_all("a", href=True):
        href = link["href"].strip()
        if not href or href.startswith("javascript:"):
            continue
        if "/static/" in href:
            continue
        lowered = href.lower()
        if "/image/" in lowered or lowered.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            return urljoin(thread_url, href)

    for image in container.find_all("img", src=True):
        src = image["src"].strip()
        if not src or src.startswith("data:"):
            continue
        if "/static/media/" in src:
            continue
        lowered = src.lower()
        if "/image/" in lowered or lowered.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            return urljoin(thread_url, src)

    return ""


def find_time_text(container):
    if container is None:
        return ""

    for tag in container.find_all(["p", "span", "div"]):
        text = tag.get_text(" ", strip=True)
        if TIME_TEXT_RE.match(text):
            return normalize_time_text(text)
    return ""


def normalize_time_text(text):
    value = str(text or "").strip()
    if not value:
        return ""

    if value == "刚刚":
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")

    match = RELATIVE_TIME_RE.match(value)
    if not match:
        return value

    amount = int(match.group(1))
    unit = match.group(2)
    now = datetime.now()

    if unit == "年":
        target_year = max(1970, now.year - amount)
        return f"{target_year:04d}-01-01 00:00:00"

    if unit in {"个月", "月"}:
        total_months = now.year * 12 + (now.month - 1) - amount
        target_year = max(1970, total_months // 12)
        return f"{target_year:04d}-01-01 00:00:00"

    if unit == "周":
        target_year = max(1970, (now - timedelta(days=amount * 7)).year)
        return f"{target_year:04d}-01-01 00:00:00"

    if unit == "天":
        target_year = max(1970, (now - timedelta(days=amount)).year)
        return f"{target_year:04d}-01-01 00:00:00"

    if unit == "小时":
        target_year = max(1970, (now - timedelta(hours=amount)).year)
        return f"{target_year:04d}-01-01 00:00:00"

    if unit == "分钟":
        target_year = max(1970, (now - timedelta(minutes=amount)).year)
        return f"{target_year:04d}-01-01 00:00:00"

    if unit == "秒":
        target_year = max(1970, (now - timedelta(seconds=amount)).year)
        return f"{target_year:04d}-01-01 00:00:00"

    return value


def find_user_and_po(container):
    user_id = ""
    is_po = False

    if container is None:
        return user_id, is_po

    for tag in container.find_all(["p", "div", "span", "a", "button"]):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue

        classes = tag.get("class") or []
        if "reed-cookie" not in classes:
            continue

        if normalize_po_marker(text):
            is_po = True
            continue

        if is_likely_user_text(text):
            user_id = text
            break

    if user_id:
        return user_id, is_po

    preferred_keywords = ("cookie", "user", "author", "account", "name", "nick")
    for tag, text in collect_header_like_texts(container):
        class_names = [str(name).casefold() for name in (tag.get("class") or [])]
        class_text = " ".join(class_names)
        if any(keyword in class_text for keyword in preferred_keywords):
            user_id = text
            return user_id, is_po

    for _, text in collect_header_like_texts(container):
        user_id = text
        return user_id, is_po

    return user_id, is_po


def find_direct_div_with_font(container):
    if container is None:
        return None

    for child in container.find_all("div", recursive=False):
        if child.find("font") is not None:
            return child
    return None


def parse_main_post(soup, thread_id, thread_url):
    thread_post_no = f"No.{thread_id}"
    main_card = None

    for card in soup.find_all(is_card_root):
        text = card.get_text(" ", strip=True)
        if thread_post_no not in text:
            continue
        if card.find("nav") is None:
            continue
        main_card = card
        break

    if main_card is None:
        raise ValueError("未找到主串卡片。")

    main_content = main_card.find("div", class_=lambda value: value and "MuiCardContent-root" in value)
    if main_content is None:
        raise ValueError("主串卡片缺少内容区域。")

    user_id, _ = find_user_and_po(main_content)
    content_block = find_direct_div_with_font(main_content)
    content = extract_post_content(content_block)

    result = {
        "post_no": thread_post_no,
        "user_id": user_id,
        "PO": "(PO主)",
        "time": find_time_text(main_content),
        "content": content,
    }

    if THREAD_TITLE:
        if result["content"].startswith(f"{THREAD_TITLE}\n"):
            result["title"] = THREAD_TITLE
            result["content"] = result["content"][len(THREAD_TITLE) + 1 :].strip()
        elif result["content"] == THREAD_TITLE:
            result["title"] = THREAD_TITLE
            result["content"] = ""

    img_url = extract_post_image_url(main_content, thread_url)
    if img_url:
        result["img_url"] = img_url

    return result


def parse_reply_post(card, po_user_id, thread_url):
    card_id = str(card.get("id") or "").strip()
    if not card_id.isdigit():
        return None

    direct_divs = [child for child in card.find_all("div", recursive=False)]
    header = direct_divs[0] if direct_divs else card
    content_block = None
    for child in direct_divs[1:]:
        if child.find("font") is not None or child.find(string=POST_NO_RE) is not None:
            content_block = child
            break

    user_id, has_po_badge = find_user_and_po(header)
    content = extract_post_content(content_block)

    result = {
        "post_no": f"No.{card_id}",
        "user_id": user_id,
        "time": find_time_text(header),
        "content": content,
    }

    if has_po_badge:
        result["PO"] = "(PO主)"
    elif po_user_id and user_id and user_id == po_user_id:
        result["PO"] = "(PO主)"

    img_url = extract_post_image_url(card, thread_url)
    if img_url:
        result["img_url"] = img_url

    return result


def parse_current_page_no(soup):
    button = soup.select_one("nav[aria-label='pagination navigation'] button[aria-current='true']")
    if button is None:
        return 1

    text = button.get_text(strip=True)
    return int(text) if text.isdigit() else 1


def parse_total_pages(soup):
    nav = soup.select_one("nav[aria-label='pagination navigation']")
    if nav is None:
        return 1

    page_numbers = []
    for button in nav.select("button[aria-label]"):
        aria_label = button.get("aria-label", "")
        match = re.search(r"page\s+(\d+)", aria_label, re.IGNORECASE)
        if match:
            page_numbers.append(int(match.group(1)))

    return max(page_numbers) if page_numbers else 1


def parse_rendered_page(html, thread_id, thread_url):
    soup = BeautifulSoup(html, "html.parser")
    posts = [parse_main_post(soup, thread_id, thread_url)]
    po_user_id = posts[0].get("user_id", "")

    seen_post_nos = {posts[0]["post_no"]}
    for card in soup.find_all(is_post_card_content):
        parsed = parse_reply_post(card, po_user_id, thread_url)
        if parsed is None:
            continue
        if parsed["post_no"] in seen_post_nos:
            continue
        seen_post_nos.add(parsed["post_no"])
        posts.append(parsed)

    if not posts:
        raise ValueError("当前页面未解析到帖子内容。")

    current_page_no = parse_current_page_no(soup)
    total_pages = parse_total_pages(soup)
    return posts, current_page_no, total_pages


def fetch_rendered_page(page, context, thread_url, thread_id, target_page_no, current_remote_page_no=None):
    if target_page_no <= 1:
        page.goto(thread_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        wait_for_thread_ready(page, thread_id, expected_page_no=1)
        sync_session_cookies_to_session(SESSION, context)
        html = page.content()
        posts, current_page_no, total_pages = parse_rendered_page(html, thread_id, thread_url)
        return html, posts, current_page_no, total_pages

    for candidate_url in build_page_candidate_urls(thread_url, target_page_no):
        page.goto(candidate_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        wait_for_thread_ready(page, thread_id, expected_page_no=target_page_no)
        sync_session_cookies_to_session(SESSION, context)
        html = page.content()
        posts, current_page_no, total_pages = parse_rendered_page(html, thread_id, thread_url)
        if current_page_no == target_page_no:
            return html, posts, current_page_no, total_pages

    if current_remote_page_no is None or current_remote_page_no > target_page_no:
        page.goto(thread_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        wait_for_thread_ready(page, thread_id, expected_page_no=1)
        sync_session_cookies_to_session(SESSION, context)
        html = page.content()
        _, current_remote_page_no, _ = parse_rendered_page(html, thread_id, thread_url)

    html = page.content()
    posts, current_page_no, total_pages = parse_rendered_page(html, thread_id, thread_url)
    while current_page_no < target_page_no:
        next_button = page.get_by_label("Go to next page")
        if next_button.count() == 0:
            raise RuntimeError(f"无法导航到第{target_page_no}页，未找到下一页按钮。")
        next_button.first.click(timeout=10000)
        wait_for_thread_ready(page, thread_id, expected_page_no=current_page_no + 1)
        sync_session_cookies_to_session(SESSION, context)
        html = page.content()
        posts, current_page_no, total_pages = parse_rendered_page(html, thread_id, thread_url)

    return html, posts, current_page_no, total_pages


def sync_thread(thread_url, folder):
    thread_id = extract_thread_id(thread_url)
    page_no = 1
    pending_reasons = set()
    current_remote_page_no = None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "未安装 playwright。\n"
            "先执行:\n"
            "  pip install playwright\n"
            "\n"
            "如果 BROWSER_MODE = 'playwright'，还需要执行:\n"
            "  playwright install chromium\n"
            "\n"
            "如果 BROWSER_MODE = 'edge'，只要本机已安装 Edge，一般不需要再下载 Chromium。"
        ) from exc

    with sync_playwright() as p:
        browser = launch_browser(p)
        context_options = {
            "viewport": {"width": 1440, "height": 2200},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        }
        if STORAGE_STATE_PATH.exists():
            context_options["storage_state"] = str(STORAGE_STATE_PATH)
            print(f"已加载登录态: {STORAGE_STATE_PATH}")
        else:
            print(f"未找到登录态文件，将以未登录状态访问: {STORAGE_STATE_PATH}")

        context = browser.new_context(**context_options)
        page = context.new_page()

        while True:
            page_path = build_page_path(folder, page_no)
            next_page_path = build_page_path(folder, page_no + 1)
            previous_posts = None
            if page_no > 1:
                previous_posts = load_page_posts(build_page_path(folder, page_no - 1))

            if os.path.exists(page_path):
                posts = load_page_posts(page_path)
                if posts is None:
                    print(f"第{page_no}页损坏，重新抓取。")
                else:
                    if not validate_page_posts(page_no, previous_posts, posts):
                        print(f"Stop on existing page {page_no}.")
                        break

                    if ensure_page_images(SESSION, posts, folder) > 0:
                        pending_reasons.add(f"images_downloaded:{page_no}")

                    if os.path.exists(next_page_path):
                        print(f"第{page_no}页已存在且图片完整，检查下一页。")
                        page_no += 1
                        continue

                    print(f"第{page_no}页是当前本地最后一页，访问远端检查是否还有下一页。")

            else:
                print(f"第{page_no}页未下载，开始抓取。")

            html, posts, current_remote_page_no, total_pages = fetch_rendered_page(
                page=page,
                context=context,
                thread_url=thread_url,
                thread_id=thread_id,
                target_page_no=page_no,
                current_remote_page_no=current_remote_page_no,
            )

            _ = html  # Keep the fetch explicit; we only need parsed posts for now.

            if not validate_page_posts(page_no, previous_posts, posts):
                print(f"Stop before saving page {page_no}.")
                break

            if save_page_posts(page_path, posts):
                pending_reasons.add(f"page_saved:{page_no}")

            if ensure_page_images(SESSION, posts, folder) > 0:
                pending_reasons.add(f"images_downloaded:{page_no}")

            if page_no < total_pages:
                print(f"第{page_no}页处理完成，继续第{page_no + 1}页。")
                page_no += 1
                continue

            print(f"第{page_no}页确认已是最后一页，停止。")
            break

        context.close()
        browser.close()

    if pending_reasons:
        mark_thread_pending(folder, pending_reasons, CONCATE_PENDING_FILENAME)
        print(f"已写入待合并标记: {Path(folder) / CONCATE_PENDING_FILENAME}")
    else:
        print("本次未新增页面，也未补到新图片，不写待合并标记。")


def run_download():
    meta = build_thread_meta(
        thread_url=THREAD_URL,
        title=THREAD_TITLE,
        tags=TAGS,
        series=SERIES,
        installment=INSTALLMENT,
        genre=GENRE,
        status=STATUS,
        original_folder_name=ORIGINAL_PAGE_FOLDER_NAME,
    )
    thread_url = meta["thread_url"]
    folder = ORIGINAL_PAGES_ROOT / meta["folder_name"]
    ensure_folder(folder)
    save_thread_meta(folder, meta, THREAD_META_FILENAME)
    sync_thread(thread_url, folder)
    print(f"已写入元信息: {folder / THREAD_META_FILENAME}")
    print("保存成功")


if __name__ == "__main__":
    run_download()

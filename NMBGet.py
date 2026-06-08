import json
import os
import random
import time
from urllib.parse import urlparse
from downloader_common import *
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
ORIGINAL_PAGE_FOLDER_NAME = "original_pages"
ORIGINAL_PAGES_ROOT = ROOT / ORIGINAL_PAGE_FOLDER_NAME
THREAD_META_FILENAME = "thread_meta.json"
CONCATE_PENDING_FILENAME = "concate_pending.json"
STORAGE_STATE_PATH = ROOT / "nmb_storage_state.json"
MANUAL_COOKIE_STRING = ""

THREAD_URL = "https://www.nmbxd1.com/t/65648500"
THREAD_TITLE = "欢迎你来到404学院-新"
TAGS = []
SERIES = "其他"
INSTALLMENT = None
GENRE = "跑团"
STATUS = "痛"

HEADERS = {
    "cookie": "",
    "upgrade-insecure-requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

SESSION = create_session(HEADERS)


def load_storage_state_cookies(storage_state_path=STORAGE_STATE_PATH):
    return load_storage_state_cookies_into_session(
        SESSION,
        storage_state_path,
        detect_cookie_name="userhash",
    )

def parse_post_block(post_block, is_main=False):
    content_dict = {}

    post_no = post_block.select_one(".h-threads-info-id")
    post_no = post_no.text.strip() if post_no else ""
    content_dict["post_no"] = post_no

    user_id = post_block.select_one(".h-threads-info-uid")
    user_id = user_id.text.strip() if user_id else ""
    content_dict["user_id"] = user_id[3:] if user_id.startswith("ID:") else user_id[3:]

    if is_main:
        content_dict["PO"] = "(PO主)"
    else:
        po = post_block.select_one(".uk-text-primary.uk-text-small")
        if po:
            normalized_po = normalize_po_marker(po.text)
            if normalized_po:
                content_dict["PO"] = normalized_po

    item_time = post_block.select_one(".h-threads-info-createdat")
    content_dict["time"] = item_time.text.strip() if item_time else ""

    content_el = post_block.select_one(".h-threads-content")
    content_dict["content"] = extract_text_with_inline_tags(
        content_el,
        normalize_crlf=False,
        max_consecutive_newlines=1,
    )

    title = post_block.select_one(".h-threads-info-title")
    title_text = title.text.strip() if title else ""
    if title_text and title_text != "无标题":
        content_dict["title"] = title_text

    email = post_block.select_one(".h-threads-info-email")
    email_text = email.text.strip() if email else ""
    if email_text and email_text != "无名氏":
        content_dict["email"] = email_text

    img = post_block.select_one(".h-threads-img-box")
    if img:
        img_link = img.select_one(".h-threads-img-a")
        if img_link and img_link.get("href"):
            content_dict["img_url"] = img_link.get("href")

    return content_dict


def find_next_url(soup):
    next_a = soup.find("a", string="下一页")
    if next_a and next_a.get("href"):
        href = next_a["href"]
        return href.split("?", 1)[1] if "?" in href else href
    return None


def parse_posts(html):
    soup = BeautifulSoup(html, "html.parser")
    posts = []

    for post_block in soup.select("div.h-threads-item-main"):
        posts.append(parse_post_block(post_block, is_main=True))

    for post_block in soup.select("div.h-threads-item-reply"):
        posts.append(parse_post_block(post_block, is_main=False))

    return posts, find_next_url(soup)

def extract_page_no(next_url):
    if not next_url:
        return None

    for part in next_url.split("&"):
        if part.startswith("page="):
            value = part.split("=", 1)[1]
            if value.isdigit():
                return int(value)
    return None


def build_page_url(thread_url, page_no):
    if page_no <= 1:
        return thread_url
    return f"{thread_url}?page={page_no}"



def sync_thread(thread_url, folder):
    page_no = 1
    pending_reasons = set()

    while True:
        page_path = build_page_path(folder, page_no)
        next_page_path = build_page_path(folder, page_no + 1)
        previous_posts = None
        if page_no > 1:
            previous_posts = load_page_posts(build_page_path(folder, page_no - 1))

        if os.path.exists(page_path):
            posts = load_page_posts(page_path)
            if posts is None:
                html = fetch_thread_page(SESSION, build_page_url(thread_url, page_no))
                posts, next_url = parse_posts(html)
                if not validate_page_posts(page_no, previous_posts, posts):
                    print(f"Stop before saving page {page_no}.")
                    break
                if save_page_posts(page_path, posts):
                    pending_reasons.add(f"page_saved:{page_no}")
                if ensure_page_images(SESSION, posts, folder) > 0:
                    pending_reasons.add(f"images_downloaded:{page_no}")

                next_page_no = extract_page_no(next_url)
                if next_page_no:
                    page_no = next_page_no
                    continue

                print(f"第{page_no}页为最后一页，停止。")
                break

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
            html = fetch_thread_page(SESSION, build_page_url(thread_url, page_no))
            posts, next_url = parse_posts(html)
            if not validate_page_posts(page_no, previous_posts, posts):
                print(f"Stop after refetching page {page_no}.")
                break
            if save_page_posts(page_path, posts):
                pending_reasons.add(f"page_saved:{page_no}")
            if ensure_page_images(SESSION, posts, folder) > 0:
                pending_reasons.add(f"images_downloaded:{page_no}")

            next_page_no = extract_page_no(next_url)
            if next_page_no:
                print(f"发现下一页: 第{next_page_no}页")
                page_no = next_page_no
                continue

            print(f"第{page_no}页确认已是最后一页，停止。")
            break

        print(f"第{page_no}页未下载，开始抓取。")
        html = fetch_thread_page(SESSION, build_page_url(thread_url, page_no))
        posts, next_url = parse_posts(html)
        if not validate_page_posts(page_no, previous_posts, posts):
            print(f"Stop before saving page {page_no}.")
            break
        if save_page_posts(page_path, posts):
            pending_reasons.add(f"page_saved:{page_no}")
        if ensure_page_images(SESSION, posts, folder) > 0:
            pending_reasons.add(f"images_downloaded:{page_no}")

        next_page_no = extract_page_no(next_url)
        if next_page_no:
            print(f"已保存第{page_no}页，继续抓取第{next_page_no}页。")
            page_no = next_page_no
            sleep_with_jitter(3)
            continue

        print(f"已保存第{page_no}页，且没有下一页，停止。")
        break

    if pending_reasons:
        mark_thread_pending(folder, pending_reasons, CONCATE_PENDING_FILENAME)
        print(f"已写入待合并标记: {Path(folder) / CONCATE_PENDING_FILENAME}")
    else:
        print("本次未新增页面，也未补到新图片，不写待合并标记。")


def run_download():
    load_storage_state_cookies()
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

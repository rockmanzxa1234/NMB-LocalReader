import json
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from downloader_common import *
import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString

ROOT = Path(__file__).resolve().parent
ORIGINAL_PAGE_FOLDER_NAME = "original_pages"
ORIGINAL_PAGES_ROOT = ROOT / ORIGINAL_PAGE_FOLDER_NAME
THREAD_META_FILENAME = "thread_meta.json"
CONCATE_PENDING_FILENAME = "concate_pending.json"

THREAD_URL = "http://bog.ac/t/XXXXXXXX"
THREAD_TITLE = ""
TAGS = []
SERIES = "其他"
INSTALLMENT = None
GENRE = ""
STATUS = ""

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

SESSION = create_session(HEADERS)

def parse_post_no(elem):
    if elem is None:
        return ""

    text = "".join(str(node).strip() for node in elem.contents if isinstance(node, NavigableString))
    return text.strip()


def extract_item_image_url(container):
    if container is None:
        return ""

    img_link = container.select_one(".item-content-img a[href]")
    if img_link:
        return urljoin("http://bog.ac", img_link.get("href", "").strip())

    return ""


def parse_main_post(post_block):
    post = {}

    header = post_block.select_one(":scope > .item-header")
    if header is None:
        return None

    post_no = parse_post_no(header.select_one(".item-pop"))
    if not post_no:
        return None
    post["post_no"] = post_no

    user_id = header.select_one(".item-id")
    post["user_id"] = user_id.text.strip() if user_id else ""
    post["PO"] = "(PO主)"

    item_time = header.select_one(".item-time")
    post["time"] = item_time.text.strip() if item_time else ""

    title = post_block.select_one(":scope > .item-title")
    title_text = title.text.strip() if title else ""
    if title_text:
        post["title"] = title_text

    content = post_block.select_one(":scope > .item-content")
    post["content"] = extract_text_with_inline_tags(
        content,
        normalize_crlf=True,
        max_consecutive_newlines=1,
    )

    img_url = extract_item_image_url(post_block)
    if img_url:
        post["img_url"] = img_url

    return post


def parse_reply_post(reply_block):
    post = {}

    reply_header = reply_block.select_one(".item-header")
    if reply_header is None:
        return None

    post_no = parse_post_no(reply_header.select_one(".item-pop"))
    if not post_no:
        return None
    post["post_no"] = post_no

    user_id = reply_header.select_one(".item-id")
    post["user_id"] = user_id.text.strip() if user_id else ""

    po = reply_header.select_one(".item-po")
    if po:
        normalized_po = normalize_po_marker(po.text)
        if normalized_po:
            post["PO"] = normalized_po

    item_time = reply_header.select_one(".item-time")
    post["time"] = item_time.text.strip() if item_time else ""

    reply_content = reply_block.select_one(".item-content")
    post["content"] = extract_text_with_inline_tags(
        reply_content,
        normalize_crlf=True,
        max_consecutive_newlines=1,
    )

    img_url = extract_item_image_url(reply_block)
    if img_url:
        post["img_url"] = img_url

    return post


def parse_posts(html):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    seen_post_nos = set()

    for post_block in soup.select("div.item-main"):
        main_post = parse_main_post(post_block)
        if main_post and main_post["post_no"] not in seen_post_nos:
            seen_post_nos.add(main_post["post_no"])
            posts.append(main_post)

        for reply_block in post_block.select(":scope > .item-reply"):
            reply_post = parse_reply_post(reply_block)
            if reply_post is None:
                continue
            if reply_post["post_no"] in seen_post_nos:
                continue
            seen_post_nos.add(reply_post["post_no"])
            posts.append(reply_post)

    next_a = soup.find("a", string="下一页")
    next_page_no = None
    if next_a and next_a.get("href"):
        next_page_no = next_a["href"].rstrip("/").split("/")[-1].strip()
        if not str(next_page_no).isdigit():
            next_page_no = None
        else:
            next_page_no = int(next_page_no)

    return posts, next_page_no

def build_page_url(thread_url, page_no):
    return f"{thread_url.rstrip('/')}/{int(page_no)}"


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
                posts, next_page_no = parse_posts(html)
                if not validate_page_posts(page_no, previous_posts, posts):
                    print(f"Stop before saving page {page_no}.")
                    break
                if save_page_posts(page_path, posts):
                    pending_reasons.add(f"page_saved:{page_no}")
                if ensure_page_images(SESSION, posts, folder) > 0:
                    pending_reasons.add(f"images_downloaded:{page_no}")

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
            posts, next_page_no = parse_posts(html)
            if not validate_page_posts(page_no, previous_posts, posts):
                print(f"Stop after refetching page {page_no}.")
                break
            if save_page_posts(page_path, posts):
                pending_reasons.add(f"page_saved:{page_no}")
            if ensure_page_images(SESSION, posts, folder) > 0:
                pending_reasons.add(f"images_downloaded:{page_no}")

            if next_page_no:
                print(f"发现下一页: 第{next_page_no}页")
                page_no = next_page_no
                continue

            print(f"第{page_no}页确认已是最后一页，停止。")
            break

        print(f"第{page_no}页未下载，开始抓取。")
        html = fetch_thread_page(SESSION, build_page_url(thread_url, page_no))
        posts, next_page_no = parse_posts(html)
        if not validate_page_posts(page_no, previous_posts, posts):
            print(f"Stop before saving page {page_no}.")
            break
        if save_page_posts(page_path, posts):
            pending_reasons.add(f"page_saved:{page_no}")
        if ensure_page_images(SESSION, posts, folder) > 0:
            pending_reasons.add(f"images_downloaded:{page_no}")

        if next_page_no:
            print(f"已保存第{page_no}页，继续抓取第{next_page_no}页。")
            page_no = next_page_no
            sleep_with_jitter(1)
            continue

        print(f"已保存第{page_no}页，且没有下一页，停止。")
        break

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

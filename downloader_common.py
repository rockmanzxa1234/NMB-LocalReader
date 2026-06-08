import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

def normalize_tags(tags):
    if tags is None:
        return []

    if isinstance(tags, str):
        return [tags.strip()] if tags.strip() else []

    return [str(tag).strip() for tag in tags if str(tag).strip()]


def create_session(headers):
    session = requests.Session()
    session.headers.update(headers)
    if not str(headers.get("cookie") or "").strip():
        session.headers.pop("cookie", None)
    return session


def build_thread_meta(
    thread_url,
    title,
    tags,
    series,
    installment,
    genre,
    status,
    original_folder_name,
):
    title_text = str(title or "").strip()
    if not title_text:
        raise ValueError("THREAD_TITLE 不能为空。")
    if installment is not None and (
        isinstance(installment, bool) or not isinstance(installment, (int, float))
    ):
        raise ValueError("INSTALLMENT 必须是数字（整数或小数）或 None。")

    folder_name = title_text
    return {
        "thread_url": str(thread_url or "").strip(),
        "title": title_text,
        "folder_name": folder_name,
        "folder_relative": str(Path(original_folder_name) / folder_name).replace("\\", "/"),
        "downloaded_at": int(time.time()),
        "tags": normalize_tags(tags),
        "series": str(series or "").strip(),
        "installment": installment,
        "genre": str(genre or "").strip(),
        "status": str(status or "").strip(),
    }

def ensure_folder(folder):
    os.makedirs(folder, exist_ok=True)
    os.makedirs(os.path.join(folder, "pages"), exist_ok=True)


def extract_text_with_inline_tags(
    elem,
    *,
    normalize_crlf=True,
    max_consecutive_newlines=1,
):
    parts = []

    if elem is None:
        return ""

    for node in elem.descendants:
        if hasattr(node, "name") and node.name == "br":
            parts.append("\n")
            continue

        text = str(node) if isinstance(node, str) else None
        if text is None:
            continue
        if text.strip():
            parts.append(text)

    content = "".join(parts)
    if normalize_crlf:
        content = content.replace("\r\n", "\n")

    if max_consecutive_newlines is not None and max_consecutive_newlines >= 1:
        content = re.sub(
            r"\n{%d,}" % (max_consecutive_newlines + 1),
            "\n" * max_consecutive_newlines,
            content,
        )

    return content.strip()

def ensure_page_images(session, posts, folder):
    downloaded_count = 0

    for post in posts:
        img_url = post.get("img_url")
        post_no = post.get("post_no", "")
        if not img_url or not post_no:
            continue

        image_path = get_image_path(folder, normalize_post_no(post_no), img_url)
        if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            continue

        print(f"补下载图片: {os.path.basename(image_path)}")
        if download_image(session, img_url, folder, normalize_post_no(post_no)):
            downloaded_count += 1

    return downloaded_count

def build_page_path(folder, page_no):
    return os.path.join(folder, "pages", f"page{page_no}.json")

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def normalize_post_no(post_no):
    text = str(post_no or "").strip()
    if text.startswith("#"):
        return text[1:]
    if text.startswith("No."):
        return text[3:]
    return text

def download_image(session,img_url, folder, post_no, retries=5):
    image_path = get_image_path(folder, post_no, img_url)

    if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
        return True

    for attempt in range(1, retries + 1):
        try:
            resp = session.get(img_url, timeout=20)
            resp.raise_for_status()
            with open(image_path, "wb") as f:
                f.write(resp.content)
            return True
        except requests.exceptions.RequestException as exc:
            print(
                f"图片下载失败，第{attempt}/{retries}次: "
                f"{post_no} | {img_url} | {exc}"
            )
            sleep_with_jitter(5)

    return False

def get_image_extension(img_url):
    suffix = Path(urlparse(img_url).path).suffix.lower().lstrip(".")
    return suffix or "img"

def get_image_path(folder, post_no, img_url):
    image_name = f"{post_no}.{get_image_extension(img_url)}"
    return os.path.join(folder, image_name)

def load_page_posts(page_path):
    try:
        with open(page_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取页面文件失败，将重新抓取: {page_path} | {exc}")
        return None

def save_thread_meta(folder_path, meta, thread_meta_filename):
    folder_path = Path(folder_path)
    write_json(folder_path / thread_meta_filename, meta)

def save_page_posts(page_path, posts):
    page_path_obj = Path(page_path)
    if page_path_obj.exists():
        existing_posts = load_page_posts(page_path)
        if existing_posts == posts:
            return False

    with open(page_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=4)
    return True

def mark_thread_pending(folder_path, reasons, concate_pending_filename):
    folder_path = Path(folder_path)
    reason_list = sorted({str(reason).strip() for reason in reasons if str(reason).strip()})
    payload = {
        "pending": True,
        "updated_at": int(time.time()),
        "reasons": reason_list,
    }
    write_json(folder_path / concate_pending_filename, payload)


def sleep_with_jitter(seconds):
    time.sleep(max(0, seconds))


def load_storage_state_cookies_into_session(
    session,
    storage_state_path,
    *,
    detect_cookie_name=None,
):
    storage_state_path = Path(storage_state_path)
    if not storage_state_path.exists():
        print(f"Login state file not found: {storage_state_path}")
        return False

    try:
        payload = json.loads(storage_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Failed to read login state: {storage_state_path} | {exc}")
        return False

    cookies = payload.get("cookies")
    if not isinstance(cookies, list):
        print(f"Invalid login state format: {storage_state_path}")
        return False

    session.headers.pop("cookie", None)
    session.cookies.clear()
    loaded_count = 0
    detected = False
    target_name = str(detect_cookie_name or "").strip()

    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue

        name = str(cookie.get("name") or "").strip()
        value = cookie.get("value")
        domain = str(cookie.get("domain") or "").strip() or None
        path_value = str(cookie.get("path") or "/").strip() or "/"
        if not name or value is None:
            continue

        session.cookies.set(name, value, domain=domain, path=path_value)
        loaded_count += 1
        if target_name and name == target_name:
            detected = True

    print(f"Loaded login state: {storage_state_path} | cookies={loaded_count}")
    if target_name:
        print(f"Detected {target_name}: {'yes' if detected else 'no'}")

    return loaded_count > 0


def sync_session_cookies_to_session(session, context):
    try:
        cookies = context.cookies()
    except Exception:
        return

    session.cookies.clear()
    for cookie in cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        domain = cookie.get("domain")
        if not name or value is None:
            continue
        session.cookies.set(name, value, domain=domain)


def normalize_po_marker(value):
    text = str(value or "").strip()
    if not text:
        return ""

    compact = text.strip("()[]{} ").casefold()
    if compact in {"po", "po主"}:
        return "(PO主)"

    return ""

def fetch_thread_page(session, url):
    while True:
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as exc:
            print(f"获取页面失败，稍后重试: {url} | {exc}")
            sleep_with_jitter(10)

def get_effective_post_nos(posts):
    post_nos = [post.get("post_no") for post in posts if post.get("post_no")]

    if post_nos:
        post_nos = post_nos[1:]

    while post_nos and post_nos[0] == "No.9999999":
        post_nos = post_nos[1:]

    return post_nos

def find_repeated_post_nos(previous_posts, current_posts):
    previous_ids = set(get_effective_post_nos(previous_posts))
    current_ids = get_effective_post_nos(current_posts)

    repeated = []
    seen = set()
    for post_no in current_ids:
        if post_no in previous_ids and post_no not in seen:
            repeated.append(post_no)
            seen.add(post_no)

    return repeated

def validate_page_posts(page_no, previous_posts, current_posts):
    if page_no <= 1 or previous_posts is None:
        return True

    repeated_post_nos = find_repeated_post_nos(previous_posts, current_posts)
    if not repeated_post_nos:
        return True

    sample_ids = ", ".join(repeated_post_nos[:10])
    print(
        f"Page {page_no} looks invalid. "
        f"Repeated post_no after the first post/tip: {sample_ids}"
    )
    return False

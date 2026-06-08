import hashlib
import os
import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PAGE_FILE_RE = re.compile(r"page(\d+)\.json$", re.IGNORECASE)
POST_NO_RE = re.compile(r"^(?:No\.|#)(\d+)$", re.IGNORECASE)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
THREAD_META_FILENAME = "thread_meta.json"
CONCATE_PENDING_FILENAME = "concate_pending.json"
META_CHUNK_SIZE = 1000
AWEIDAO_HOST = "aweidao1.com"
ORIGINAL_POST_NO_KEY = "_original_post_no"
REQUIRE_PENDING_MARKER = True
TIME_PATTERNS = [
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})\([^)]+\)(\d{2}):(\d{2}):(\d{2})$"),
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$"),
]


def normalize_tags(tags):
    if tags is None:
        return []

    if isinstance(tags, str):
        return [tags.strip()] if tags.strip() else []

    return [str(tag).strip() for tag in tags if str(tag).strip()]


def validate_config(meta):
    title = str(meta.get("title", "")).strip()
    installment = meta.get("installment")
    if not title:
        raise ValueError("thread_meta.json 中缺少 title。")

    if installment is not None and (
        isinstance(installment, bool) or not isinstance(installment, (int, float))
    ):
        raise ValueError("installment ????????????? None?")
    if not isinstance(META_CHUNK_SIZE, int) or META_CHUNK_SIZE <= 0:
        raise ValueError("META_CHUNK_SIZE 必须是正整数。")


def get_post_number(post_no):
    match = POST_NO_RE.match(str(post_no).strip())
    if not match:
        return None
    return int(match.group(1))


def is_aweidao_thread(meta):
    thread_url = str(meta.get("thread_url", "")).strip().lower()
    return AWEIDAO_HOST in thread_url


def rewrite_aweidao_post_no(post_no):
    text = str(post_no).strip()
    match = POST_NO_RE.match(text)
    if not match:
        return text

    number_text = match.group(1)
    if int(number_text) <= 50000000:
        return text

    prefix = text[:match.start(1)]
    return f"{prefix}90{number_text}"


def transform_post_for_thread(post, meta):
    if not is_aweidao_thread(meta):
        return post

    original_post_no = str(post.get("post_no", "")).strip()
    rewritten_post_no = rewrite_aweidao_post_no(original_post_no)
    if rewritten_post_no == original_post_no:
        return post

    transformed = dict(post)
    transformed[ORIGINAL_POST_NO_KEY] = original_post_no
    transformed["post_no"] = rewritten_post_no
    return transformed


def is_all_nines_post(post_no):
    number = get_post_number(post_no)
    if number is None:
        return False
    digits = str(number)
    return digits and set(digits) == {"9"}


def page_sort_key(path):
    match = PAGE_FILE_RE.search(path.name)
    if match:
        return int(match.group(1))
    return float("inf")


def post_sort_key(post):
    number = get_post_number(post.get("post_no"))
    if number is None:
        return float("inf")
    return number


def load_page_posts(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} 顶层不是 list。")
    return data


def merge_page_files(pages_dir, meta):
    merged = []
    seen_post_nos = set()

    page_files = sorted(pages_dir.glob("*.json"), key=page_sort_key)
    if not page_files:
        raise FileNotFoundError(f"{pages_dir} 下没有找到分页 json 文件。")

    for page_file in page_files:
        print(f"读取: {page_file}")
        for post in load_page_posts(page_file):
            if not isinstance(post, dict):
                continue

            post = transform_post_for_thread(post, meta)

            post_no = post.get("post_no")
            if not post_no:
                continue

            if is_all_nines_post(post_no):
                continue

            if post_no in seen_post_nos:
                continue

            seen_post_nos.add(post_no)
            merged.append(post)

    merged.sort(key=post_sort_key)
    return merged


def get_po_user_id(posts):
    for post in posts:
        if post.get("PO"):
            return str(post.get("user_id", "")).strip()
    if posts:
        return str(posts[0].get("user_id", "")).strip()
    return ""


def get_updated_at(posts):
    if not posts:
        return ""
    return str(posts[-1].get("time", "")).strip()


def parse_post_time_to_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return 0

    match = None
    for pattern in TIME_PATTERNS:
        match = pattern.match(text)
        if match:
            break
    if match is None:
        return 0

    try:
        dt = datetime(
            year=int(match.group(1)),
            month=int(match.group(2)),
            day=int(match.group(3)),
            hour=int(match.group(4)),
            minute=int(match.group(5)),
            second=int(match.group(6)),
        )
    except ValueError:
        return 0

    return int(dt.timestamp())


def build_thread_id(title, folder, po_user_id, updated_at, post_count):
    seed = "\n".join(
        [
            title.strip(),
            folder.strip(),
            po_user_id.strip(),
            updated_at.strip(),
            str(post_count),
        ]
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def get_image_extension_from_url(img_url):
    path = urlparse(str(img_url)).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in IMAGE_EXTENSIONS else suffix or ".jpg"


def get_post_no_for_image(post, use_original=False):
    if use_original:
        return str(post.get(ORIGINAL_POST_NO_KEY) or post.get("post_no", "")).strip()
    return str(post.get("post_no", "")).strip()


def get_image_filename(post, use_original=False):
    post_no = get_post_no_for_image(post, use_original=use_original)
    number = get_post_number(post_no)
    img_url = post.get("img_url")
    if number is None or not img_url:
        return None
    return f"{number}{get_image_extension_from_url(img_url)}"


def find_existing_image_path(thread_dir, image_name):
    exact_path = thread_dir / image_name
    if exact_path.exists():
        return exact_path

    stem = Path(image_name).stem
    candidates = []
    for extension in IMAGE_EXTENSIONS:
        candidate = thread_dir / f"{stem}{extension}"
        print(f"Checking for image: {candidate}")
        if candidate.exists():
            candidates.append(candidate)

    if not candidates:
        return None

    candidates.sort(key=lambda path: path.suffix.lower())
    return candidates[0]


def copy_thread_images(thread_dir, posts, server_thread_dir):
    copied = 0
    missing = []
    image_map = {}

    for post in posts:
        post_no = str(post.get("post_no", "")).strip()
        if not post_no or post_no in image_map:
            continue

        target_image_name = get_image_filename(post)
        if not target_image_name:
            continue

        source_image_name = get_image_filename(post, use_original=True)
        source = find_existing_image_path(thread_dir, source_image_name)
        if source is not None:
            target_number = get_post_number(post_no)
            target_name = f"{target_number}{source.suffix.lower()}" if target_number is not None else target_image_name
            target = server_thread_dir / target_name
            shutil.copy2(source, target)
            image_map[post_no] = target.name
            copied += 1
        else:
            missing.append(source_image_name or target_image_name)

    return copied, missing, image_map


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_pending_threads():
    original_pages_root = ROOT / "original_pages"
    pending_threads = []

    if not original_pages_root.exists():
        raise FileNotFoundError(f"未找到目录: {original_pages_root}")

    for thread_dir in sorted(path for path in original_pages_root.iterdir() if path.is_dir()):
        pending_marker = thread_dir / CONCATE_PENDING_FILENAME
        meta_path = thread_dir / THREAD_META_FILENAME
        pages_dir = thread_dir / "pages"
        if REQUIRE_PENDING_MARKER and not pending_marker.is_file():
            continue
        if not meta_path.is_file() or not pages_dir.is_dir():
            continue

        meta = load_json(meta_path)
        if not isinstance(meta, dict):
            raise ValueError(f"{meta_path} 顶层必须是对象。")
        pending_threads.append((meta, thread_dir, pending_marker))

    return pending_threads


def write_posts_database(db_path, posts):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                post_no TEXT PRIMARY KEY,
                content TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM posts")
        conn.executemany(
            "INSERT OR REPLACE INTO posts (post_no, content) VALUES (?, ?)",
            [
                (
                    str(post.get("post_no", "")).strip(),
                    str(post.get("content", "")).replace("\r\n", "\n"),
                )
                for post in posts
                if str(post.get("post_no", "")).strip()
            ],
        )
        conn.commit()


def build_info_record(title, tags, series, installment, genre, status, posts, image_count):
    folder = title
    po_user_id = get_po_user_id(posts)
    post_count = len(posts)
    updated_at = get_updated_at(posts)

    return {
        "id": build_thread_id(title, folder, po_user_id, updated_at, post_count),
        "title": title,
        "folder": folder,
        "po_user_id": po_user_id,
        "post_count": post_count,
        "image_count": image_count,
        "updated_at": updated_at,
        "tags": tags,
        "series": series,
        "installment": installment,
        "genre": genre,
        "status": status,
    }


def build_thread_record(title, info_record, posts, image_map):
    chunks = build_meta_chunks(posts, image_map)
    return {
        "version": 3,
        "title": title,
        "folder": info_record["folder"],
        "content_db": "posts.db",
        "po_user_id": info_record["po_user_id"],
        "post_count": info_record["post_count"],
        "image_count": info_record["image_count"],
        "updated_at": info_record["updated_at"],
        "tags": info_record["tags"],
        "series": info_record["series"],
        "installment": info_record["installment"],
        "genre": info_record["genre"],
        "status": info_record["status"],
        "image_root": "../images",
        "chunk_count": len(chunks),
        "chunk_size": META_CHUNK_SIZE,
        "columns": ["post_no", "user_id", "po", "image_ext", "ts"],
        "chunks": [chunk["manifest"] for chunk in chunks],
    }


def build_thread_post_record(post, image_map):
    post_no = str(post.get("post_no", "")).strip()
    record = [
        post_no,
        str(post.get("user_id", "")).strip(),
        1 if str(post.get("PO", "")).strip() else 0,
        "",
        parse_post_time_to_timestamp(post.get("time", "")),
    ]
    image_file = image_map.get(post_no)
    if image_file:
        record[3] = Path(image_file).suffix.lower().lstrip(".")
    return record


def build_meta_chunks(posts, image_map):
    chunks = []
    total = len(posts)
    for chunk_index, start in enumerate(range(0, total, META_CHUNK_SIZE), start=1):
        chunk_posts = posts[start:start + META_CHUNK_SIZE]
        rows = [build_thread_post_record(post, image_map) for post in chunk_posts]
        chunk_filename = f"{chunk_index:04d}.json"
        manifest = {
            "file": f"meta/{chunk_filename}",
            "start_index": start,
            "end_index": start + len(chunk_posts) - 1,
            "start_post_no": str(chunk_posts[0].get("post_no", "")).strip(),
            "end_post_no": str(chunk_posts[-1].get("post_no", "")).strip(),
        }
        chunks.append(
            {
                "filename": chunk_filename,
                "posts": rows,
                "manifest": manifest,
            }
        )
    return chunks


def build_server_package(thread_dir, data_dir, title, merged_posts, info_record):
    package_root = thread_dir
    server_thread_dir = data_dir / title

    if server_thread_dir.exists():
        shutil.rmtree(server_thread_dir)

    server_thread_dir.mkdir(parents=True, exist_ok=True)

    image_count, missing_images, image_map = copy_thread_images(thread_dir, merged_posts, server_thread_dir)
    info_record["image_count"] = image_count

    meta_chunks = build_meta_chunks(merged_posts, image_map)
    thread_record = build_thread_record(title, info_record, merged_posts, image_map)

    write_json(server_thread_dir / "thread.json", thread_record)
    write_json(server_thread_dir / "info.json", info_record)
    write_posts_database(server_thread_dir / "posts.db", merged_posts)
    write_meta_chunks(server_thread_dir, meta_chunks)

    return package_root, server_thread_dir, missing_images


def write_meta_chunks(server_thread_dir, meta_chunks):
    meta_dir = server_thread_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    for chunk in meta_chunks:
        chunk_path = meta_dir / chunk["filename"]
        write_json(
            chunk_path,
            {
                "columns": ["post_no", "user_id", "po", "image_ext", "ts"],
                "posts": chunk["posts"],
            },
        )


def process_thread(meta, thread_dir):
    validate_config(meta)

    title = str(meta.get("title", "")).strip()
    tags = normalize_tags(meta.get("tags"))
    series = str(meta.get("series", "")).strip()
    installment = meta.get("installment")
    genre = str(meta.get("genre", "")).strip()
    status = str(meta.get("status", "")).strip()

    pages_dir = thread_dir / "pages"
    data_dir = ROOT / "data"

    if not thread_dir.exists():
        raise FileNotFoundError(f"未找到帖子目录: {thread_dir}")
    if not pages_dir.exists():
        raise FileNotFoundError(f"未找到 pages 目录: {pages_dir}")
    if not data_dir.exists():
        os.makedirs(data_dir)

    merged_posts = merge_page_files(pages_dir, meta)
    if not merged_posts:
        raise ValueError("合并结果为空。")

    # legacy_output = ROOT / f"{title}.json"
    # write_json(legacy_output, merged_posts)

    info_record = build_info_record(
        title=title,
        tags=tags,
        series=series,
        installment=installment,
        genre=genre,
        status=status,
        posts=merged_posts,
        image_count=0,
    )

    package_root, server_thread_dir, missing_images = build_server_package(
        thread_dir=thread_dir,
        data_dir=data_dir,
        title=title,
        merged_posts=merged_posts,
        info_record=info_record,
    )

    print("\n处理完成")
    print(f"合并后帖子数: {len(merged_posts)}")
    # print(f"旧版合并文件: {legacy_output}")
    print(f"合并后目录: {server_thread_dir}")
    print(f"thread.json: {server_thread_dir / 'thread.json'}")
    print(f"posts.db: {server_thread_dir / 'posts.db'}")
    print(f"info.json: {server_thread_dir / 'info.json'}")

    if missing_images:
        print(f"缺失图片数量: {len(missing_images)}")
        for image_name in missing_images[:20]:
            print(f"  missing: {image_name}")
        if len(missing_images) > 20:
            print("  ...")


def main():
    pending_threads = load_pending_threads()
    if not pending_threads:
        if REQUIRE_PENDING_MARKER:
            print(f"未找到带 {CONCATE_PENDING_FILENAME} 标记的帖子目录。")
        else:
            print("未找到可处理的帖子目录。")
        return

    success_count = 0
    failed = []

    for meta, thread_dir, pending_marker in pending_threads:
        print(f"\n开始处理: {thread_dir}")
        try:
            process_thread(meta, thread_dir)
            if pending_marker.is_file():
                pending_marker.unlink(missing_ok=True)
                print(f"已清除待合并标记: {pending_marker}")
            success_count += 1
        except Exception as exc:
            failed.append((thread_dir, exc))
            print(f"处理失败: {thread_dir} | {exc}")

    print(f"\n批处理完成，成功 {success_count} 个，失败 {len(failed)} 个。")
    if failed:
        print("失败目录:")
        for thread_dir, exc in failed:
            print(f"  {thread_dir} | {exc}")


if __name__ == "__main__":
    main()

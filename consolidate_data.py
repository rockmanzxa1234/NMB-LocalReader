import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from build_index import build_index, write_index


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
GLOBAL_DB_PATH = DATA_DIR / "posts.db"
INDEX_PATH = DATA_DIR / "index.json"
LEGACY_POST_INDEX_PATH = DATA_DIR / "post_index.json"

THREAD_FILENAME = "thread.json"
INFO_FILENAME = "info.json"
LOCAL_DB_FILENAME = "posts.db"
META_DIRNAME = "meta"
GLOBAL_DB_RELATIVE_PATH = "../posts.db"
GLOBAL_IMAGES_RELATIVE_PATH = "../images"
DEFAULT_CHUNK_SIZE = 1000
DB_BATCH_SIZE = 2000
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
PAGE_FILE_RE = re.compile(r"page(\d+)\.json$", re.IGNORECASE)
TIME_PATTERNS = [
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})\([^)]+\)(\d{2}):(\d{2}):(\d{2})$"),
    re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$"),
]


def get_post_number(post_no):
    value = str(post_no or "").strip()
    if value.startswith("No."):
        value = value[3:]
    elif value.startswith("#"):
        value = value[1:]

    try:
        return int(value)
    except ValueError:
        return None


def post_sort_key(post_no):
    number = get_post_number(post_no)
    if number is None:
        return (1, str(post_no or ""))
    return (0, number)


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


def ensure_global_posts_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            post_no TEXT PRIMARY KEY,
            content TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS post_meta (
            post_no TEXT PRIMARY KEY,
            folder TEXT NOT NULL,
            user_id TEXT NOT NULL,
            po INTEGER NOT NULL,
            image_ext TEXT NOT NULL,
            ts INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(post_meta)").fetchall()}
    if "ts" not in columns:
        conn.execute("ALTER TABLE post_meta ADD COLUMN ts INTEGER NOT NULL DEFAULT 0")


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_existing_image_path(directory, image_name):
    exact_path = directory / image_name
    if exact_path.is_file():
        return exact_path

    stem = Path(image_name).stem
    for extension in IMAGE_EXTENSIONS:
        candidate = directory / f"{stem}{extension}"
        if candidate.is_file():
            return candidate
    return None


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_row_value(row, column_index, name):
    index = column_index.get(name)
    if index is None or index >= len(row):
        return ""
    return row[index]


def normalize_po(value):
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value or "").strip()
    return 1 if text and text != "0" else 0


def normalize_image_ext(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if "." in text:
        return Path(text).suffix.lower().lstrip(".")
    return text.lower().lstrip(".")


def normalize_post_record(record):
    return {
        "post_no": str(record.get("post_no", "")).strip(),
        "user_id": str(record.get("user_id", "")).strip(),
        "po": normalize_po(record.get("PO", record.get("po", ""))),
        "image_ext": normalize_image_ext(record.get("image_ext", record.get("image_file", ""))),
        "ts": int(record.get("ts", record.get("timestamp", 0)) or 0),
    }


def normalize_posts_from_columns(columns, raw_posts):
    normalized = []
    column_index = {str(name): idx for idx, name in enumerate(columns)}
    for row in raw_posts:
        if not isinstance(row, list):
            continue
        normalized.append(
            {
                "post_no": str(get_row_value(row, column_index, "post_no") or "").strip(),
                "user_id": str(get_row_value(row, column_index, "user_id") or "").strip(),
                "po": normalize_po(get_row_value(row, column_index, "po")),
                "image_ext": normalize_image_ext(get_row_value(row, column_index, "image_ext")),
                "ts": int(get_row_value(row, column_index, "ts") or 0),
            }
        )
    return normalized


def load_thread_posts(thread_dir, thread_data):
    chunks = thread_data.get("chunks", [])
    columns = thread_data.get("columns")
    raw_posts = thread_data.get("posts", [])

    if isinstance(chunks, list) and chunks:
        normalized = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_file = str(chunk.get("file", "")).strip()
            if not chunk_file:
                continue
            chunk_path = thread_dir / chunk_file
            if not chunk_path.is_file():
                raise FileNotFoundError(f"缺少分片文件: {chunk_path}")
            chunk_data = load_json(chunk_path)
            chunk_columns = chunk_data.get("columns", columns or [])
            chunk_posts = chunk_data.get("posts", [])
            if isinstance(chunk_columns, list) and isinstance(chunk_posts, list):
                normalized.extend(normalize_posts_from_columns(chunk_columns, chunk_posts))
        return normalized

    if isinstance(columns, list) and isinstance(raw_posts, list):
        return normalize_posts_from_columns(columns, raw_posts)

    if isinstance(raw_posts, list):
        return [
            normalize_post_record(row)
            for row in raw_posts
            if isinstance(row, dict)
        ]

    return []


def load_time_map_from_title_dir(title_dir):
    pages_dir = title_dir / "pages"
    if not pages_dir.is_dir():
        return {}

    time_map = {}
    for page_path in sorted(pages_dir.glob("*.json"), key=page_sort_key):
        page_data = load_json(page_path)
        if not isinstance(page_data, list):
            continue
        for record in page_data:
            if not isinstance(record, dict):
                continue
            post_no = str(record.get("post_no", "")).strip()
            if not post_no or post_no in time_map or is_all_nines_post(post_no):
                continue
            time_map[post_no] = parse_post_time_to_timestamp(record.get("time", ""))
    return time_map


def backfill_thread_timestamps(thread_dir, posts):
    if not posts:
        return 0
    if any(int(post.get("ts", 0) or 0) > 0 for post in posts):
        return 0

    title_dir = thread_dir
    time_map = load_time_map_from_title_dir(title_dir)
    if not time_map:
        return 0

    updated = 0
    for post in posts:
        if int(post.get("ts", 0) or 0) > 0:
            continue
        post_no = str(post.get("post_no", "")).strip()
        ts_value = int(time_map.get(post_no, 0) or 0)
        if ts_value > 0:
            post["ts"] = ts_value
            updated += 1
    return updated


def build_thread_posts_rows(posts):
    return [
        [
            str(post["post_no"]).strip(),
            str(post["user_id"]).strip(),
            1 if post["po"] else 0,
            str(post["image_ext"]).strip().lower(),
            int(post.get("ts", 0) or 0),
        ]
        for post in posts
    ]


def build_meta_chunks(posts, chunk_size):
    chunks = []
    total = len(posts)
    for chunk_index, start in enumerate(range(0, total, chunk_size), start=1):
        chunk_posts = posts[start:start + chunk_size]
        filename = f"{chunk_index:04d}.json"
        chunks.append(
            {
                "filename": filename,
                "rows": build_thread_posts_rows(chunk_posts),
                "manifest": {
                    "file": f"{META_DIRNAME}/{filename}",
                    "start_index": start,
                    "end_index": start + len(chunk_posts) - 1,
                    "start_post_no": str(chunk_posts[0]["post_no"]).strip(),
                    "end_post_no": str(chunk_posts[-1]["post_no"]).strip(),
                },
            }
        )
    return chunks


def parse_chunk_size(thread_data):
    try:
        value = int(thread_data.get("chunk_size", DEFAULT_CHUNK_SIZE))
    except (TypeError, ValueError):
        value = DEFAULT_CHUNK_SIZE
    return max(1, value)


def find_thread_directories():
    thread_dirs = []
    for path in sorted(DATA_DIR.iterdir()):
        if not path.is_dir():
            continue
        if path.name == IMAGES_DIR.name:
            continue
        if (path / THREAD_FILENAME).is_file() and (path / INFO_FILENAME).is_file():
            thread_dirs.append(path)
    return thread_dirs


def merge_local_database(thread_dir, global_conn):
    local_db_path = thread_dir / LOCAL_DB_FILENAME
    if not local_db_path.is_file():
        return {"inserted": 0, "skipped": 0, "conflicts": []}

    inserted = 0
    skipped = 0
    conflicts = []

    with sqlite3.connect(local_db_path) as local_conn:
        cursor = local_conn.execute(
            "SELECT post_no, content FROM posts ORDER BY post_no"
        )

        while True:
            rows = cursor.fetchmany(DB_BATCH_SIZE)
            if not rows:
                break

            batch = [(str(post_no).strip(), content) for post_no, content in rows if str(post_no).strip()]
            if not batch:
                continue

            placeholders = ",".join("?" for _ in batch)
            existing_rows = global_conn.execute(
                f"SELECT post_no, content FROM posts WHERE post_no IN ({placeholders})",
                [post_no for post_no, _ in batch],
            ).fetchall()
            existing_map = {str(post_no): content for post_no, content in existing_rows}

            new_rows = []
            for post_no, content in batch:
                existing_content = existing_map.get(post_no)
                if existing_content is None:
                    new_rows.append((post_no, content))
                    continue

                if existing_content == content:
                    skipped += 1
                    continue

                conflicts.append(post_no)

            if new_rows:
                global_conn.executemany(
                    "INSERT INTO posts (post_no, content) VALUES (?, ?)",
                    new_rows,
                )
                inserted += len(new_rows)

    return {"inserted": inserted, "skipped": skipped, "conflicts": conflicts}


def upsert_thread_post_meta(global_conn, folder_name, posts):
    rows = [
        (
            str(post["post_no"]).strip(),
            str(folder_name).strip(),
            str(post["user_id"]).strip(),
            1 if post["po"] else 0,
            str(post["image_ext"]).strip().lower(),
            int(post.get("ts", 0) or 0),
        )
        for post in posts
        if str(post["post_no"]).strip()
    ]
    if not rows:
        return 0

    global_conn.executemany(
        """
        INSERT INTO post_meta (post_no, folder, user_id, po, image_ext, ts)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(post_no) DO UPDATE SET
            folder = excluded.folder,
            user_id = excluded.user_id,
            po = excluded.po,
            image_ext = excluded.image_ext,
            ts = excluded.ts
        """,
        rows,
    )
    return len(rows)


def move_thread_images(thread_dir, posts):
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    moved = 0
    deduped = 0
    missing = []
    conflicts = []

    for post in posts:
        post_no = str(post["post_no"]).strip()
        image_ext = str(post["image_ext"]).strip().lower()
        if not post_no or not image_ext:
            continue

        number = get_post_number(post_no)
        if number is None:
            missing.append(f"{post_no} (invalid post_no)")
            continue

        filename = f"{number}.{image_ext}"
        source = thread_dir / filename
        target = IMAGES_DIR / filename

        if not source.is_file():
            source = find_existing_image_path(thread_dir, filename)
            if source is None:
                source = find_existing_image_path(IMAGES_DIR, filename)
            if source is None:
                missing.append(filename)
                continue

        if target.exists():
            if source.resolve() == target.resolve():
                continue
            if hash_file(source) == hash_file(target):
                if source.exists() and source.parent != IMAGES_DIR:
                    source.unlink()
                deduped += 1
            else:
                conflicts.append(filename)
            continue

        if source.parent == IMAGES_DIR:
            continue

        shutil.copy2(source, target)
        if source.exists() and source.parent != IMAGES_DIR:
            source.unlink()
        moved += 1

    return {
        "moved": moved,
        "deduped": deduped,
        "missing": missing,
        "conflicts": conflicts,
    }


def rewrite_thread_structure(thread_dir, thread_data, posts):
    sorted_posts = sorted(posts, key=lambda post: post_sort_key(post["post_no"]))
    chunk_size = parse_chunk_size(thread_data)
    meta_chunks = build_meta_chunks(sorted_posts, chunk_size)

    meta_dir = thread_dir / META_DIRNAME
    if meta_dir.exists():
        shutil.rmtree(meta_dir)
    meta_dir.mkdir(parents=True, exist_ok=True)

    for chunk in meta_chunks:
        write_json(
            meta_dir / chunk["filename"],
            {
                "columns": ["post_no", "user_id", "po", "image_ext", "ts"],
                "posts": chunk["rows"],
            },
        )

    updated = dict(thread_data)
    updated["version"] = 3
    updated["content_db"] = GLOBAL_DB_RELATIVE_PATH
    updated["image_root"] = GLOBAL_IMAGES_RELATIVE_PATH
    updated["columns"] = ["post_no", "user_id", "po", "image_ext", "ts"]
    updated["post_count"] = len(sorted_posts)
    updated["chunk_size"] = chunk_size
    updated["chunk_count"] = len(meta_chunks)
    updated["chunks"] = [chunk["manifest"] for chunk in meta_chunks]
    updated.pop("posts", None)

    write_json(thread_dir / THREAD_FILENAME, updated)
    return sorted_posts, meta_chunks


def consolidate():
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"未找到 data 目录: {DATA_DIR}")

    thread_dirs = find_thread_directories()
    if not thread_dirs:
        raise FileNotFoundError(f"{DATA_DIR} 下没有找到包含 thread.json 的帖子目录。")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    report = []

    with sqlite3.connect(GLOBAL_DB_PATH) as global_conn:
        ensure_global_posts_table(global_conn)

        for thread_dir in thread_dirs:
            print(f"处理: {thread_dir}")
            thread_data = load_json(thread_dir / THREAD_FILENAME)
            info_data = load_json(thread_dir / INFO_FILENAME)
            posts = load_thread_posts(thread_dir, thread_data)
            backfilled_ts = backfill_thread_timestamps(thread_dir, posts)
            posts, _meta_chunks = rewrite_thread_structure(thread_dir, thread_data, posts)

            db_report = merge_local_database(thread_dir, global_conn)
            folder_name = str(info_data.get("folder", thread_dir.name)).strip() or thread_dir.name
            meta_rows = upsert_thread_post_meta(global_conn, folder_name, posts)
            image_report = move_thread_images(thread_dir, posts)
            report.append(
                {
                    "folder": thread_dir.name,
                    "backfilled_ts": backfilled_ts,
                    "db": db_report,
                    "meta_rows": meta_rows,
                    "images": image_report,
                }
            )
            global_conn.commit()

    index_records = build_index(DATA_DIR)
    write_index(INDEX_PATH, index_records)
    if LEGACY_POST_INDEX_PATH.exists():
        LEGACY_POST_INDEX_PATH.unlink()

    return report, len(index_records)


def main():
    report, index_count = consolidate()

    print("\n整合完成")
    print(f"统一图片目录: {IMAGES_DIR}")
    print(f"统一正文库: {GLOBAL_DB_PATH}")
    print(f"目录索引: {INDEX_PATH} | {index_count} 条")

    for item in report:
        print(f"\n[{item['folder']}]")
        print(f"  timestamps: backfilled={item['backfilled_ts']}")
        print(
            "  db:"
            f" inserted={item['db']['inserted']}"
            f" skipped={item['db']['skipped']}"
            f" conflicts={len(item['db']['conflicts'])}"
        )
        print(f"  meta: upserted={item['meta_rows']}")
        print(
            "  images:"
            f" moved={item['images']['moved']}"
            f" deduped={item['images']['deduped']}"
            f" missing={len(item['images']['missing'])}"
            f" conflicts={len(item['images']['conflicts'])}"
        )

        for post_no in item["db"]["conflicts"][:10]:
            print(f"    db conflict: {post_no}")
        for filename in item["images"]["conflicts"][:10]:
            print(f"    image conflict: {filename}")


if __name__ == "__main__":
    main()

import os
import sys

# Keep the local random.py from shadowing stdlib imports.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path = [entry for entry in sys.path if os.path.abspath(entry or os.curdir) != SCRIPT_DIR]

import base64
import hashlib
import hmac
import json
import mimetypes
import re
import sqlite3
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
USERS_FILE = BASE_DIR / "auth_users.json"
INVITE_CODES_FILE = BASE_DIR / "invite_codes.json"
BOOKMARKS_DIR = DATA_DIR / "_bookmarks"
READ_STATE_DIR = DATA_DIR / "_read_state"

THREAD_FILENAME = "thread.json"
INFO_FILENAME = "info.json"
GLOBAL_INDEX_FILENAME = "index.json"
GLOBAL_POST_DB_FILENAME = "posts.db"
GLOBAL_IMAGES_DIRNAME = "images"
DEFAULT_COLUMNS = ["post_no", "user_id", "po", "image_ext", "ts"]


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


HOST = os.getenv("THREAD_READER_HOST", "127.0.0.1")
PORT = int(os.getenv("THREAD_READER_PORT", "4567"))
SESSION_COOKIE_NAME = "thread_reader_session"
SESSION_TTL_SECONDS = int(os.getenv("THREAD_READER_SESSION_TTL", str(12 * 60 * 60)))
COOKIE_SECURE = env_bool("THREAD_READER_COOKIE_SECURE", False)
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
MIN_PASSWORD_LENGTH = 6

STATIC_FILES = {
    "index.html",
    "server_home.html",
    "post_reader_server.html",
    "server_portal.css",
    "server_auth.js",
    "server_login.js",
    "server_home.js",
    "post_reader_server.css",
    "post_reader_server.js",
}

SESSIONS = {}
THREAD_CACHE = {}


def now_ts():
    return int(time.time())


def make_token():
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")


def cleanup_sessions():
    current = now_ts()
    expired = [token for token, session in SESSIONS.items() if session["expires_at"] <= current]
    for token in expired:
        SESSIONS.pop(token, None)


def hash_password(password, iterations=310000, salt_hex=None):
    salt_hex = salt_hex or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt_hex}${digest}"


def verify_password(password, password_hash):
    try:
        algorithm, iterations, salt_hex, digest = password_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    calculated = hash_password(password, iterations=int(iterations), salt_hex=salt_hex)
    return hmac.compare_digest(calculated, password_hash)


def load_users_payload():
    if not USERS_FILE.exists():
        return {"users": []}

    with USERS_FILE.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("Invalid users file: payload must be an object.")

    users = payload.get("users", [])
    if not isinstance(users, list):
        raise ValueError("Invalid users file: users must be a list.")

    payload["users"] = users
    return payload


def save_users_payload(payload):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with USERS_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_invite_codes_payload():
    if not INVITE_CODES_FILE.exists():
        return {"codes": []}

    with INVITE_CODES_FILE.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("Invalid invite codes file: payload must be an object.")

    codes = payload.get("codes", [])
    if not isinstance(codes, list):
        raise ValueError("Invalid invite codes file: codes must be a list.")

    payload["codes"] = codes
    return payload


def save_invite_codes_payload(payload):
    INVITE_CODES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with INVITE_CODES_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_users():
    payload = load_users_payload()
    users = payload["users"]

    normalized = {}
    for user in users:
        if not isinstance(user, dict):
            continue
        username = str(user.get("username", "")).strip()
        password_hash = str(user.get("password_hash", "")).strip()
        enabled = bool(user.get("enabled", True))
        if username and password_hash and enabled:
            normalized[username] = password_hash
    return normalized


def validate_registration_username(username):
    text = str(username or "").strip()
    if not USERNAME_RE.fullmatch(text):
        raise ValueError("用户名只能使用 3 到 32 位字母、数字、下划线或连字符。")
    return text


def validate_registration_password(password):
    text = str(password or "")
    if len(text) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位。")
    return text


def ensure_registration_username_available(username):
    payload = load_users_payload()
    users = payload["users"]

    for user in users:
        if not isinstance(user, dict):
            continue
        existing_username = str(user.get("username", "")).strip()
        if existing_username == username:
            raise FileExistsError("用户名已存在。")


def find_available_invite_code(payload, invite_code):
    code_text = str(invite_code or "")
    if not code_text:
        raise ValueError("邀请码不能为空。")

    current = now_ts()
    for item in payload["codes"]:
        if not isinstance(item, dict):
            continue

        candidate = str(item.get("code", ""))
        if candidate != code_text:
            continue

        if not bool(item.get("enabled", True)):
            raise ValueError("邀请码已停用。")

        expires_at = int(item.get("expires_at", 0) or 0)
        if expires_at > 0 and expires_at <= current:
            raise ValueError("邀请码已过期。")

        max_uses = int(item.get("max_uses", 0) or 0)
        used_count = int(item.get("used_count", 0) or 0)
        if max_uses > 0 and used_count >= max_uses:
            raise ValueError("邀请码已达到使用上限。")

        item["used_count"] = used_count
        item["max_uses"] = max_uses
        item["expires_at"] = expires_at
        return item

    raise ValueError("邀请码错误。")


def consume_invite_code(invite_code):
    payload = load_invite_codes_payload()
    item = find_available_invite_code(payload, invite_code)
    item["used_count"] = int(item.get("used_count", 0) or 0) + 1
    item["last_used_at"] = now_ts()
    save_invite_codes_payload(payload)
    return dict(item)


def validate_invite_code(invite_code):
    payload = load_invite_codes_payload()
    find_available_invite_code(payload, invite_code)
    return str(invite_code or "")


def register_user(username, password):
    username = validate_registration_username(username)
    password = validate_registration_password(password)
    ensure_registration_username_available(username)
    payload = load_users_payload()
    users = payload["users"]

    users.append(
        {
            "username": username,
            "password_hash": hash_password(password),
            "enabled": True,
        }
    )
    save_users_payload(payload)
    return username


def safe_child_path(parent, *parts):
    candidate = parent.joinpath(*parts).resolve()
    parent_resolved = parent.resolve()
    if candidate != parent_resolved and parent_resolved not in candidate.parents:
        raise ValueError("Invalid path.")
    return candidate


def resolve_configured_path(base_dir, raw_path, *allowed_roots):
    candidate = base_dir.joinpath(str(raw_path or "")).resolve()
    roots = [base_dir.resolve(), *(Path(root).resolve() for root in allowed_roots if root)]
    if any(candidate == root or root in candidate.parents for root in roots):
        return candidate
    raise ValueError("Configured path points outside the data directory.")


def safe_thread_dir(folder_name):
    normalized = str(folder_name or "").strip()
    if not normalized:
        raise ValueError("Thread folder cannot be empty.")

    path_parts = Path(normalized).parts
    if len(path_parts) != 1 or path_parts[0] in {".", ".."}:
        raise ValueError("Invalid thread folder.")

    thread_dir = safe_child_path(DATA_DIR, normalized)
    if not thread_dir.is_dir():
        raise FileNotFoundError("Thread folder not found.")
    return thread_dir


def parse_int(value, default, minimum=1, maximum=None):
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def load_json_file(path, expected_type=None):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if expected_type is not None and not isinstance(data, expected_type):
        type_name = getattr(expected_type, "__name__", str(expected_type))
        raise ValueError(f"Invalid JSON shape in {path.name}: expected {type_name}.")
    return data


def write_json_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_post_number(post_no):
    value = str(post_no or "").strip()
    match = re.match(r"^(?:No\.|#)(\d+)$", value, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def post_sort_key(post_no):
    number = get_post_number(post_no)
    if number is None:
        return (1, str(post_no or ""))
    return (0, number)


def normalize_po(value):
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    text = str(value or "").strip().lower()
    return 1 if text and text not in {"0", "false", "no"} else 0


def normalize_image_ext(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "." in text:
        return Path(text).suffix.lower().lstrip(".")
    return text.lstrip(".")


def get_row_value(row, column_index, name):
    index = column_index.get(name)
    if index is None or index >= len(row):
        return ""
    return row[index]


def normalize_meta_row_from_list(row, columns):
    column_index = {str(name): idx for idx, name in enumerate(columns or DEFAULT_COLUMNS)}
    return {
        "post_no": str(get_row_value(row, column_index, "post_no") or "").strip(),
        "user_id": str(get_row_value(row, column_index, "user_id") or "").strip(),
        "po": normalize_po(get_row_value(row, column_index, "po")),
        "image_ext": normalize_image_ext(get_row_value(row, column_index, "image_ext")),
        "ts": parse_int(get_row_value(row, column_index, "ts"), 0, minimum=0),
    }


def normalize_meta_row_from_dict(row):
    return {
        "post_no": str(row.get("post_no", "")).strip(),
        "user_id": str(row.get("user_id", "")).strip(),
        "po": normalize_po(row.get("po", row.get("PO", ""))),
        "image_ext": normalize_image_ext(row.get("image_ext", row.get("image_file", ""))),
        "ts": parse_int(row.get("ts", row.get("timestamp", 0)), 0, minimum=0),
    }


def normalize_meta_row(row, columns):
    if isinstance(row, list):
        return normalize_meta_row_from_list(row, columns)
    if isinstance(row, dict):
        return normalize_meta_row_from_dict(row)
    return {
        "post_no": "",
        "user_id": "",
        "po": 0,
        "image_ext": "",
        "ts": 0,
    }


def load_chunk_rows(thread_dir, chunk_path, default_columns):
    chunk_data = load_json_file(chunk_path, dict)
    chunk_columns = chunk_data.get("columns", default_columns)
    raw_posts = chunk_data.get("posts", [])
    if not isinstance(chunk_columns, list) or not isinstance(raw_posts, list):
        raise ValueError(f"Invalid chunk file: {chunk_path}")

    rows = []
    for raw_row in raw_posts:
        row = normalize_meta_row(raw_row, chunk_columns)
        if row["post_no"]:
            rows.append(row)
    return rows


def resolve_thread_content_db(thread_dir, manifest):
    configured = str(manifest.get("content_db", "") or "").strip()
    candidates = []
    if configured:
        candidates.append(resolve_configured_path(thread_dir, configured, DATA_DIR))
    candidates.append(DATA_DIR / GLOBAL_POST_DB_FILENAME)
    candidates.append(thread_dir / GLOBAL_POST_DB_FILENAME)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def resolve_thread_image_dir(thread_dir, manifest):
    configured = str(manifest.get("image_root", "") or "").strip()
    candidates = []
    if configured:
        candidates.append(resolve_configured_path(thread_dir, configured, DATA_DIR))
    candidates.append(DATA_DIR / GLOBAL_IMAGES_DIRNAME)
    candidates.append(thread_dir)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def get_thread_cache_mtime(thread_dir, manifest, info_path):
    mtimes = []
    thread_path = safe_child_path(thread_dir, THREAD_FILENAME)
    if thread_path.is_file():
        mtimes.append(thread_path.stat().st_mtime)
    if info_path.is_file():
        mtimes.append(info_path.stat().st_mtime)

    chunks = manifest.get("chunks", [])
    if isinstance(chunks, list):
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_file = str(chunk.get("file", "")).strip()
            if not chunk_file:
                continue
            chunk_path = safe_child_path(thread_dir, chunk_file)
            if chunk_path.is_file():
                mtimes.append(chunk_path.stat().st_mtime)

    return max(mtimes) if mtimes else 0


def get_lookup_keys_from_post_no(post_no):
    value = str(post_no or "").strip()
    if not value:
        return []

    keys = {value.lower()}
    no_match = re.match(r"^No\.(\d+)$", value, re.IGNORECASE)
    po_match = re.match(r"^Po\.(\d+)$", value, re.IGNORECASE)
    hash_match = re.match(r"^#(\d+)$", value)

    if no_match:
        keys.add(f"no.{no_match.group(1)}".lower())
    if po_match:
        keys.add(f"po.{po_match.group(1)}".lower())
    if hash_match:
        keys.add(f"#{hash_match.group(1)}".lower())
        keys.add(f"po.{hash_match.group(1)}".lower())

    return list(keys)


def normalize_reference_token(token):
    return str(token or "").replace(">>", "", 1).strip().lower()


def canonical_post_no_from_token(token):
    normalized = normalize_reference_token(token)
    if not normalized:
        return ""

    no_match = re.match(r"^no\.(\d+)$", normalized, re.IGNORECASE)
    po_match = re.match(r"^po\.(\d+)$", normalized, re.IGNORECASE)
    hash_match = re.match(r"^#(\d+)$", normalized)

    if no_match:
        return f"No.{no_match.group(1)}"
    if po_match:
        return f"No.{po_match.group(1)}"
    if hash_match:
        return f"No.{hash_match.group(1)}"

    return ""


def bookmark_file_path(username):
    digest = hashlib.sha256(str(username or "").encode("utf-8")).hexdigest()
    return BOOKMARKS_DIR / f"{digest}.json"


def read_state_file_path(username):
    digest = hashlib.sha256(str(username or "").encode("utf-8")).hexdigest()
    return READ_STATE_DIR / f"{digest}.json"


def load_user_bookmarks(username):
    path = bookmark_file_path(username)
    if not path.is_file():
        return []
    try:
        payload = load_json_file(path, dict)
    except Exception:
        return []

    raw_bookmarks = payload.get("bookmarks", [])
    if not isinstance(raw_bookmarks, list):
        return []

    normalized = []
    for item in raw_bookmarks:
        if not isinstance(item, dict):
            continue
        folder = str(item.get("folder", "")).strip()
        post_no = str(item.get("post_no", "")).strip()
        created_at = int(item.get("created_at", 0) or 0)
        if folder and post_no:
            normalized.append(
                {
                    "folder": folder,
                    "post_no": post_no,
                    "created_at": created_at,
                }
            )
    return normalized


def save_user_bookmarks(username, bookmarks):
    path = bookmark_file_path(username)
    write_json_file(path, {"bookmarks": bookmarks})


def toggle_user_bookmark(username, folder, post_no):
    bookmarks = load_user_bookmarks(username)
    normalized_folder = str(folder or "").strip()
    normalized_post_no = str(post_no or "").strip()

    kept = []
    removed = False
    for item in bookmarks:
        if item["folder"] == normalized_folder and item["post_no"] == normalized_post_no:
            removed = True
            continue
        kept.append(item)

    if removed:
        save_user_bookmarks(username, kept)
        return {"added": False, "removed": True, "bookmarks": kept}

    kept.append(
        {
            "folder": normalized_folder,
            "post_no": normalized_post_no,
            "created_at": now_ts(),
        }
    )
    save_user_bookmarks(username, kept)
    return {"added": True, "removed": False, "bookmarks": kept}


def load_user_read_folders(username):
    path = read_state_file_path(username)
    if not path.is_file():
        return []
    try:
        payload = load_json_file(path, dict)
    except Exception:
        return []

    raw_folders = payload.get("folders", [])
    if not isinstance(raw_folders, list):
        return []

    normalized = []
    for item in raw_folders:
        if not isinstance(item, dict):
            continue
        folder = str(item.get("folder", "")).strip()
        updated_at = int(item.get("updated_at", 0) or 0)
        if folder:
            normalized.append({"folder": folder, "updated_at": updated_at})
    return normalized


def save_user_read_folders(username, folders):
    path = read_state_file_path(username)
    write_json_file(path, {"folders": folders})


def toggle_user_read_folder(username, folder):
    normalized_folder = str(folder or "").strip()
    folders = load_user_read_folders(username)
    kept = []
    removed = False

    for item in folders:
        if item["folder"] == normalized_folder:
            removed = True
            continue
        kept.append(item)

    if removed:
        save_user_read_folders(username, kept)
        return {"read": False, "folders": kept}

    kept.append({"folder": normalized_folder, "updated_at": now_ts()})
    save_user_read_folders(username, kept)
    return {"read": True, "folders": kept}


def get_user_read_folder_set(username):
    return {item["folder"] for item in load_user_read_folders(username)}


def build_lookup_index(rows):
    index = {}
    for row in rows:
        for key in get_lookup_keys_from_post_no(row["post_no"]):
            index[key] = row
    return index


def load_thread_bundle(folder_name):
    thread_dir = safe_thread_dir(folder_name)
    thread_path = safe_child_path(thread_dir, THREAD_FILENAME)
    info_path = safe_child_path(thread_dir, INFO_FILENAME)

    if not thread_path.is_file():
        raise FileNotFoundError(f"Thread manifest not found: {thread_path}")

    manifest = load_json_file(thread_path, dict)
    info = load_json_file(info_path, dict) if info_path.is_file() else {}
    cache_mtime = get_thread_cache_mtime(thread_dir, manifest, info_path)

    cache_key = thread_dir.name
    cached = THREAD_CACHE.get(cache_key)
    if cached and cached["mtime"] == cache_mtime:
        return cached

    columns = manifest.get("columns", DEFAULT_COLUMNS)
    chunks = manifest.get("chunks", [])
    rows = []

    if isinstance(chunks, list) and chunks:
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_file = str(chunk.get("file", "")).strip()
            if not chunk_file:
                continue
            chunk_path = safe_child_path(thread_dir, chunk_file)
            if not chunk_path.is_file():
                raise FileNotFoundError(f"Chunk file not found: {chunk_path}")
            rows.extend(load_chunk_rows(thread_dir, chunk_path, columns))
    else:
        raw_posts = manifest.get("posts", [])
        if not isinstance(raw_posts, list):
            raise ValueError("Invalid thread manifest: posts must be a list.")
        for raw_row in raw_posts:
            row = normalize_meta_row(raw_row, columns)
            if row["post_no"]:
                rows.append(row)

    rows.sort(key=lambda row: post_sort_key(row["post_no"]))

    title = (
        str(info.get("title", "")).strip()
        or str(manifest.get("title", "")).strip()
        or thread_dir.name
    )
    folder = (
        str(info.get("folder", "")).strip()
        or str(manifest.get("folder", "")).strip()
        or thread_dir.name
    )

    bundle = {
        "mtime": cache_mtime,
        "thread_dir": thread_dir,
        "folder": folder,
        "title": title,
        "info": info,
        "manifest": manifest,
        "po_user_id": str(manifest.get("po_user_id", info.get("po_user_id", ""))).strip(),
        "rows": rows,
        "lookup_index": build_lookup_index(rows),
        "content_db_path": resolve_thread_content_db(thread_dir, manifest),
        "image_dir": resolve_thread_image_dir(thread_dir, manifest),
    }
    THREAD_CACHE[cache_key] = bundle
    return bundle


def fetch_post_details(db_path, post_nos):
    normalized_post_nos = [str(post_no or "").strip() for post_no in post_nos if str(post_no or "").strip()]
    if not normalized_post_nos:
        return {}
    if not db_path.is_file():
        raise FileNotFoundError(f"Content database not found: {db_path}")

    placeholders = ",".join("?" for _ in normalized_post_nos)
    query = f"""
        SELECT
            p.post_no,
            p.content,
            COALESCE(m.folder, '') AS folder,
            COALESCE(m.user_id, '') AS user_id,
            COALESCE(m.po, 0) AS po,
            COALESCE(m.image_ext, '') AS image_ext,
            COALESCE(m.ts, 0) AS ts
        FROM posts p
        LEFT JOIN post_meta m ON p.post_no = m.post_no
        WHERE p.post_no IN ({placeholders})
    """
    with sqlite3.connect(db_path) as conn:
        try:
            rows = conn.execute(query, normalized_post_nos).fetchall()
        except sqlite3.OperationalError as error:
            if "no such table: post_meta" not in str(error).lower():
                raise
            fallback_query = f"SELECT post_no, content FROM posts WHERE post_no IN ({placeholders})"
            rows = conn.execute(fallback_query, normalized_post_nos).fetchall()
            return {
                str(post_no or "").strip(): {
                    "post_no": str(post_no or "").strip(),
                    "content": str(content or "").replace("\r\n", "\n").strip(),
                    "folder": "",
                    "user_id": "",
                    "po": 0,
                    "image_ext": "",
                    "ts": 0,
                }
                for post_no, content in rows
            }

    details = {}
    for row in rows:
        post_no = str(row[0] or "").strip()
        if not post_no:
            continue
        details[post_no] = {
            "post_no": post_no,
            "content": str(row[1] or "").replace("\r\n", "\n").strip(),
            "folder": str(row[2] or "").strip(),
            "user_id": str(row[3] or "").strip(),
            "po": normalize_po(row[4]),
            "image_ext": normalize_image_ext(row[5]),
            "ts": parse_int(row[6], 0, minimum=0),
        }
    return details


def fetch_post_from_global_db(db_path, canonical_post_no):
    if not canonical_post_no:
        return None
    if not db_path.is_file():
        raise FileNotFoundError(f"Content database not found: {db_path}")

    query = """
        SELECT
            p.post_no,
            p.content,
            COALESCE(m.folder, '') AS folder,
            COALESCE(m.user_id, '') AS user_id,
            COALESCE(m.po, 0) AS po,
            COALESCE(m.image_ext, '') AS image_ext,
            COALESCE(m.ts, 0) AS ts
        FROM posts p
        LEFT JOIN post_meta m ON p.post_no = m.post_no
        WHERE p.post_no = ?
        LIMIT 1
    """
    with sqlite3.connect(db_path) as conn:
        try:
            row = conn.execute(query, (canonical_post_no,)).fetchone()
        except sqlite3.OperationalError as error:
            if "no such table: post_meta" not in str(error).lower():
                raise
            row = conn.execute(
                "SELECT post_no, content, '' AS folder, '' AS user_id, 0 AS po, '' AS image_ext, 0 AS ts FROM posts WHERE post_no = ? LIMIT 1",
                (canonical_post_no,),
            ).fetchone()

    if row is None:
        return None

    return {
        "post_no": str(row[0] or "").strip(),
        "content": str(row[1] or "").replace("\r\n", "\n").strip(),
        "folder": str(row[2] or "").strip(),
        "user_id": str(row[3] or "").strip(),
        "po": normalize_po(row[4]),
        "image_ext": normalize_image_ext(row[5]),
        "ts": parse_int(row[6], 0, minimum=0),
    }


def format_timestamp(ts_value):
    ts_int = parse_int(ts_value, 0, minimum=0)
    if ts_int <= 0:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_int))


def hydrate_posts(bundle, meta_rows):
    post_nos = [row["post_no"] for row in meta_rows if row.get("post_no")]
    details_map = fetch_post_details(bundle["content_db_path"], post_nos)

    hydrated = []
    for row in meta_rows:
        post_no = row["post_no"]
        db_row = details_map.get(post_no, {})
        user_id = row["user_id"] or db_row.get("user_id", "")
        po_value = row["po"] if row["po"] else db_row.get("po", 0)
        image_ext = row["image_ext"] or db_row.get("image_ext", "")
        ts_value = row["ts"] if row["ts"] > 0 else db_row.get("ts", 0)
        hydrated.append(
            {
                "folder": bundle["folder"],
                "thread_title": bundle["title"],
                "post_no": post_no,
                "user_id": user_id,
                "PO": "PO" if po_value else "",
                "time": format_timestamp(ts_value),
                "title": "",
                "email": "",
                "content": db_row.get("content", ""),
                "img_url": "",
                "image_ext": image_ext,
            }
        )
    return hydrated


def get_thread_bookmarks_payload(username, folder):
    bundle = load_thread_bundle(folder)
    bookmarks = [
        item
        for item in load_user_bookmarks(username)
        if item["folder"] == bundle["folder"]
    ]

    if not bookmarks:
        return []

    bookmark_map = {item["post_no"]: item["created_at"] for item in bookmarks}
    rows = []
    for row in bundle["rows"]:
        if row["post_no"] in bookmark_map:
            rows.append(row)

    hydrated = hydrate_posts(bundle, rows)
    order_map = {post["post_no"]: index for index, post in enumerate(hydrated)}
    hydrated.sort(key=lambda post: order_map.get(post["post_no"], 10**9))
    for post in hydrated:
        post["bookmarked_at"] = bookmark_map.get(post["post_no"], 0)
    return hydrated


def parse_user_filter_tokens(raw_value):
    return [
        token.strip().lower()
        for token in re.split(r"[\s,，]+", str(raw_value or ""))
        if token.strip()
    ]


def parse_user_filter_tokens(raw_value):
    return [
        token.strip().lower()
        for token in re.split(r"[\s,;，；]+", str(raw_value or ""))
        if token.strip()
    ]


def matches_active_filters(row, user_tokens, po_mode):
    normalized_user_id = row["user_id"].lower()
    user_ok = (not user_tokens) or any(token in normalized_user_id for token in user_tokens)
    is_po = bool(row["po"])

    if po_mode == "po":
        po_ok = is_po
    elif po_mode == "non-po":
        po_ok = not is_po
    else:
        po_ok = True

    return user_ok and po_ok


def get_page_for_post_in_list(rows, target_post_no, page_size):
    if not target_post_no:
        return 1
    for index, row in enumerate(rows):
        if row["post_no"] == target_post_no:
            return (index // page_size) + 1
    return 1


def slice_page(rows, page_no, page_size):
    start = (page_no - 1) * page_size
    end = start + page_size
    return rows[start:end]


def build_thread_view(bundle, query):
    page_size = parse_int(query.get("page_size", ["20"])[0], 20, minimum=1, maximum=200)
    requested_page = parse_int(query.get("page", ["1"])[0], 1, minimum=1)
    filter_scope = str(query.get("filter_scope", ["all"])[0] or "all").strip()
    if filter_scope not in {"all", "page"}:
        filter_scope = "all"

    po_mode = str(query.get("po_mode", ["all"])[0] or "all").strip()
    if po_mode not in {"all", "po", "non-po"}:
        po_mode = "all"

    reason = str(query.get("reason", ["filter-change"])[0] or "filter-change").strip()
    filter_change_behavior = str(query.get("filter_change_behavior", ["keep-page"])[0] or "keep-page").strip()
    if filter_change_behavior not in {"keep-page", "first-page"}:
        filter_change_behavior = "keep-page"

    page_size_behavior = str(query.get("page_size_behavior", ["keep-first-item"])[0] or "keep-first-item").strip()
    if page_size_behavior not in {"keep-first-item", "first-page"}:
        page_size_behavior = "keep-first-item"

    anchor_post_no = str(query.get("anchor_post_no", [""])[0] or "").strip()
    user_filter_input = str(query.get("user_filter", [""])[0] or "")
    user_tokens = parse_user_filter_tokens(user_filter_input)
    jump_filter_bypassed = False

    all_rows = bundle["rows"]
    raw_total_posts = len(all_rows)
    raw_total_pages = max(1, (raw_total_posts + page_size - 1) // page_size) if raw_total_posts else 0
    current_page = requested_page

    if reason == "filter-change" and filter_change_behavior == "first-page":
        current_page = 1

    if reason == "page-size-change":
        if page_size_behavior == "first-page":
            current_page = 1
        elif anchor_post_no:
            current_page = get_page_for_post_in_list(all_rows, anchor_post_no, page_size)
    elif reason == "bookmark-jump" and anchor_post_no:
        current_page = get_page_for_post_in_list(all_rows, anchor_post_no, page_size)

    if raw_total_pages > 0:
        current_page = min(max(1, current_page), raw_total_pages)
    else:
        current_page = 1

    current_raw_page_rows = slice_page(all_rows, current_page, page_size)

    if filter_scope == "page":
        filtered_rows = [row for row in current_raw_page_rows if matches_active_filters(row, user_tokens, po_mode)]
        if reason == "bookmark-jump" and anchor_post_no:
            if any(row["post_no"] == anchor_post_no for row in filtered_rows):
                page_rows = filtered_rows
            else:
                page_rows = current_raw_page_rows
                jump_filter_bypassed = True
        else:
            page_rows = filtered_rows
        active_total_pages = raw_total_pages
        filtered_total_posts = len(filtered_rows)
        filtered_total_pages = raw_total_pages
    else:
        filtered_rows = [row for row in all_rows if matches_active_filters(row, user_tokens, po_mode)]
        if reason == "page-size-change" and page_size_behavior == "keep-first-item" and anchor_post_no:
            current_page = get_page_for_post_in_list(filtered_rows, anchor_post_no, page_size)

        filtered_total_posts = len(filtered_rows)
        filtered_total_pages = max(1, (filtered_total_posts + page_size - 1) // page_size) if filtered_total_posts else 0
        if reason == "bookmark-jump" and anchor_post_no:
            if any(row["post_no"] == anchor_post_no for row in filtered_rows):
                if filtered_total_pages > 0:
                    current_page = get_page_for_post_in_list(filtered_rows, anchor_post_no, page_size)
                    current_page = min(max(1, current_page), filtered_total_pages)
                active_total_pages = filtered_total_pages
                page_rows = slice_page(filtered_rows, current_page, page_size)
            else:
                current_page = get_page_for_post_in_list(all_rows, anchor_post_no, page_size)
                current_page = min(max(1, current_page), raw_total_pages) if raw_total_pages > 0 else 1
                active_total_pages = raw_total_pages
                page_rows = slice_page(all_rows, current_page, page_size)
                jump_filter_bypassed = True
        else:
            if filtered_total_pages > 0:
                current_page = min(max(1, current_page), filtered_total_pages)
            else:
                current_page = 1

            active_total_pages = filtered_total_pages
            page_rows = slice_page(filtered_rows, current_page, page_size)

    page_posts = hydrate_posts(bundle, page_rows)

    return {
        "folder": bundle["folder"],
        "thread_title": bundle["title"],
        "page": current_page,
        "page_size": page_size,
        "filter_scope": filter_scope,
        "po_mode": po_mode,
        "user_filter_input": user_filter_input,
        "raw_total_posts": raw_total_posts,
        "raw_total_pages": raw_total_pages,
        "filtered_total_posts": filtered_total_posts,
        "filtered_total_pages": filtered_total_pages,
        "active_total_pages": active_total_pages,
        "current_raw_page_posts": len(current_raw_page_rows),
        "jump_filter_bypassed": jump_filter_bypassed,
        "posts": page_posts,
    }


def find_referenced_post(folder, token):
    canonical_post_no = canonical_post_no_from_token(token)
    if not canonical_post_no:
        return None

    current_bundle = load_thread_bundle(folder)
    direct = current_bundle["lookup_index"].get(canonical_post_no.lower())
    if direct:
        hydrated = hydrate_posts(current_bundle, [direct])
        return hydrated[0] if hydrated else None

    resolved = fetch_post_from_global_db(current_bundle["content_db_path"], canonical_post_no)
    if not resolved:
        return None

    target_folder = resolved["folder"] or current_bundle["folder"]
    target_title = current_bundle["title"] if target_folder == current_bundle["folder"] else target_folder
    return {
        "folder": target_folder,
        "thread_title": target_title,
        "post_no": resolved["post_no"],
        "user_id": resolved["user_id"],
        "PO": "PO" if resolved["po"] else "",
        "time": format_timestamp(resolved.get("ts", 0)),
        "title": "",
        "email": "",
        "content": resolved["content"],
        "img_url": "",
        "image_ext": resolved["image_ext"],
    }


def resolve_image_file(folder, filename):
    safe_name = Path(str(filename or "")).name
    if not safe_name or safe_name != str(filename or ""):
        raise ValueError("Invalid image filename.")

    global_image_dir = DATA_DIR / GLOBAL_IMAGES_DIRNAME
    global_candidate = safe_child_path(global_image_dir, safe_name)
    if global_candidate.is_file():
        return global_candidate

    bundle = load_thread_bundle(folder)
    local_candidates = [
        safe_child_path(bundle["image_dir"], safe_name),
        safe_child_path(bundle["thread_dir"], safe_name),
    ]
    for candidate in local_candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError("Image file not found.")


class ThreadReaderHandler(BaseHTTPRequestHandler):
    server_version = "ThreadReaderServer/1.2"

    def do_GET(self):
        cleanup_sessions()
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            self.handle_api_get(path, parse_qs(parsed.query, keep_blank_values=True))
            return

        self.handle_static_get(path)

    def do_POST(self):
        cleanup_sessions()
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/login":
            self.handle_login()
            return

        if path == "/api/register":
            self.handle_register()
            return

        if path == "/api/logout":
            self.handle_logout()
            return

        if path.startswith("/api/"):
            self.handle_api_post(path)
            return

        self.send_json(HTTPStatus.NOT_FOUND, {"message": "API not found."})

    def handle_static_get(self, path):
        if path in {"", "/"}:
            path = "/index.html"

        if path.startswith("/data/"):
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "Resource not found."})
            return

        filename = unquote(path.lstrip("/"))
        if filename not in STATIC_FILES:
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "Page resource not found."})
            return

        file_path = safe_child_path(BASE_DIR, filename)
        if not file_path.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "Page resource missing."})
            return

        self.send_file(file_path, cache_control="no-store")

    def handle_api_get(self, path, query):
        if path == "/api/session":
            self.handle_session()
            return

        session = self.require_session()
        if not session:
            return

        if path == "/api/index":
            self.handle_index()
            return

        segments = [unquote(segment) for segment in path.split("/") if segment]
        if len(segments) >= 4 and segments[0] == "api" and segments[1] == "thread":
            folder = segments[2]
            action = segments[3]

            if action == "view" and len(segments) == 4:
                self.handle_thread_view(folder, query)
                return

            if action == "post" and len(segments) == 4:
                self.handle_thread_post_lookup(folder, query)
                return

            if action == "info" and len(segments) == 4:
                self.handle_thread_info(folder)
                return

            if action == "image" and len(segments) == 5:
                self.handle_thread_image(folder, segments[4])
                return

            if action == "bookmarks" and len(segments) == 4:
                self.handle_thread_bookmarks(folder)
                return

            if action == "read-state" and len(segments) == 4:
                self.handle_thread_read_state(folder)
                return

        self.send_json(HTTPStatus.NOT_FOUND, {"message": "API not found."})

    def handle_api_post(self, path):
        session = self.require_session()
        if not session:
            return

        segments = [unquote(segment) for segment in path.split("/") if segment]
        if len(segments) >= 4 and segments[0] == "api" and segments[1] == "thread":
            folder = segments[2]
            action = segments[3]

            if action == "bookmark" and len(segments) == 4:
                self.handle_thread_bookmark_toggle(session, folder)
                return

            if action == "read-state" and len(segments) == 4:
                self.handle_thread_read_state_toggle(session, folder)
                return

        self.send_json(HTTPStatus.NOT_FOUND, {"message": "API not found."})

    def handle_session(self):
        session = self.get_session()
        if not session:
            self.send_json(HTTPStatus.OK, {"authenticated": False, "username": ""})
            return

        self.send_json(
            HTTPStatus.OK,
            {
                "authenticated": True,
                "username": session["username"],
                "expires_at": session["expires_at"],
            },
        )

    def handle_login(self):
        try:
            payload = self.read_json_body()
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": str(error)})
            return

        try:
            users = load_users()
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to load users: {error}"})
            return

        password_hash = users.get(username)
        if not password_hash or not verify_password(password, password_hash):
            self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "用户名或密码错误。"})
            return

        self.send_authenticated_session(username)

    def handle_register(self):
        try:
            payload = self.read_json_body()
            username = str(payload.get("username", "")).strip()
            password = str(payload.get("password", ""))
            invite_code = str(payload.get("invite_code", ""))
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": str(error)})
            return

        try:
            validate_registration_username(username)
            validate_registration_password(password)
            ensure_registration_username_available(username)
            validate_invite_code(invite_code)
            username = register_user(username, password)
            consume_invite_code(invite_code)
        except FileExistsError as error:
            self.send_json(HTTPStatus.CONFLICT, {"message": str(error)})
            return
        except ValueError as error:
            status = HTTPStatus.FORBIDDEN if "邀请码" in str(error) else HTTPStatus.BAD_REQUEST
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to register user: {error}"})
            return

        self.send_authenticated_session(username)

    def send_authenticated_session(self, username):
        token = make_token()
        expires_at = now_ts() + SESSION_TTL_SECONDS
        SESSIONS[token] = {
            "username": username,
            "expires_at": expires_at,
        }

        self.send_json(
            HTTPStatus.OK,
            {
                "authenticated": True,
                "username": username,
                "expires_at": expires_at,
            },
            cookies=[self.build_session_cookie(token, expires_at)],
        )

    def handle_logout(self):
        token = self.get_cookie_value(SESSION_COOKIE_NAME)
        if token:
            SESSIONS.pop(token, None)

        self.send_json(
            HTTPStatus.OK,
            {"authenticated": False, "username": ""},
            cookies=[self.build_expired_cookie()],
        )

    def handle_index(self):
        index_path = DATA_DIR / GLOBAL_INDEX_FILENAME
        if not index_path.is_file():
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "Missing data/index.json."})
            return
        session = self.require_session()
        if not session:
            return

        try:
            records = load_json_file(index_path, list)
            read_folders = get_user_read_folder_set(session["username"])
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to load index: {error}"})
            return

        enriched = []
        for record in records:
            if not isinstance(record, dict):
                continue
            item = dict(record)
            folder = str(item.get("folder", "")).strip()
            item["read"] = folder in read_folders
            enriched.append(item)

        self.send_json(HTTPStatus.OK, enriched)

    def handle_thread_view(self, folder, query):
        try:
            bundle = load_thread_bundle(folder)
            payload = build_thread_view(bundle, query)
        except (ValueError, FileNotFoundError) as error:
            status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.NOT_FOUND
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to load thread view: {error}"})
            return

        self.send_json(HTTPStatus.OK, payload)

    def handle_thread_post_lookup(self, folder, query):
        token = str(query.get("token", [""])[0] or "").strip()
        if not token:
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Missing token."})
            return

        try:
            post = find_referenced_post(folder, token)
        except (ValueError, FileNotFoundError) as error:
            status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.NOT_FOUND
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to load reference: {error}"})
            return

        self.send_json(HTTPStatus.OK, {"post": post})

    def handle_thread_bookmarks(self, folder):
        session = self.require_session()
        if not session:
            return

        try:
            bookmarks = get_thread_bookmarks_payload(session["username"], folder)
        except (ValueError, FileNotFoundError) as error:
            status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.NOT_FOUND
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to load bookmarks: {error}"})
            return

        self.send_json(HTTPStatus.OK, {"bookmarks": bookmarks})

    def handle_thread_read_state(self, folder):
        session = self.require_session()
        if not session:
            return

        try:
            bundle = load_thread_bundle(folder)
            read_folders = get_user_read_folder_set(session["username"])
        except (ValueError, FileNotFoundError) as error:
            status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.NOT_FOUND
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to load read state: {error}"})
            return

        self.send_json(HTTPStatus.OK, {"folder": bundle["folder"], "read": bundle["folder"] in read_folders})

    def handle_thread_bookmark_toggle(self, session, folder):
        try:
            payload = self.read_json_body()
            post_no = str(payload.get("post_no", "")).strip()
            if not post_no:
                raise ValueError("Missing post_no.")
            bundle = load_thread_bundle(folder)
            result = toggle_user_bookmark(session["username"], bundle["folder"], post_no)
            bookmarks = get_thread_bookmarks_payload(session["username"], bundle["folder"])
        except (ValueError, FileNotFoundError) as error:
            status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.NOT_FOUND
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to update bookmark: {error}"})
            return

        self.send_json(
            HTTPStatus.OK,
            {
                "added": result["added"],
                "removed": result["removed"],
                "bookmarks": bookmarks,
            },
        )

    def handle_thread_read_state_toggle(self, session, folder):
        try:
            bundle = load_thread_bundle(folder)
            result = toggle_user_read_folder(session["username"], bundle["folder"])
        except (ValueError, FileNotFoundError) as error:
            status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.NOT_FOUND
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to update read state: {error}"})
            return

        self.send_json(
            HTTPStatus.OK,
            {
                "folder": bundle["folder"],
                "read": bool(result["read"]),
            },
        )

    def handle_thread_info(self, folder):
        try:
            bundle = load_thread_bundle(folder)
        except (ValueError, FileNotFoundError) as error:
            status = HTTPStatus.BAD_REQUEST if isinstance(error, ValueError) else HTTPStatus.NOT_FOUND
            self.send_json(status, {"message": str(error)})
            return
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Failed to load thread info: {error}"})
            return

        manifest = bundle["manifest"]
        payload = dict(bundle["info"])
        payload.setdefault("title", bundle["title"])
        payload.setdefault("folder", bundle["folder"])
        payload.setdefault("post_count", int(manifest.get("post_count", len(bundle["rows"])) or len(bundle["rows"])))
        payload.setdefault("po_user_id", bundle["po_user_id"])
        payload.setdefault("image_count", int(manifest.get("image_count", 0) or 0))
        payload.setdefault("updated_at", str(manifest.get("updated_at", "")).strip())
        payload.setdefault("tags", manifest.get("tags", []))
        payload.setdefault("series", manifest.get("series", ""))
        payload.setdefault("installment", manifest.get("installment"))
        payload.setdefault("genre", manifest.get("genre", ""))
        payload.setdefault("status", manifest.get("status", ""))
        self.send_json(HTTPStatus.OK, payload)

    def handle_thread_image(self, folder, filename):
        try:
            file_path = resolve_image_file(folder, filename)
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": str(error)})
            return
        except FileNotFoundError as error:
            self.send_json(HTTPStatus.NOT_FOUND, {"message": str(error)})
            return

        self.send_file(file_path, cache_control="private, no-store")

    def require_session(self):
        session = self.get_session()
        if not session:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"message": "Please log in first."})
            return None
        return session

    def get_session(self):
        token = self.get_cookie_value(SESSION_COOKIE_NAME)
        if not token:
            return None

        session = SESSIONS.get(token)
        if not session:
            return None

        if session["expires_at"] <= now_ts():
            SESSIONS.pop(token, None)
            return None

        return session

    def get_cookie_value(self, name):
        raw_cookie = self.headers.get("Cookie", "")
        cookie = SimpleCookie()
        cookie.load(raw_cookie)
        morsel = cookie.get(name)
        return morsel.value if morsel else ""

    def build_session_cookie(self, token, expires_at):
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE_NAME] = token
        cookie[SESSION_COOKIE_NAME]["path"] = "/"
        cookie[SESSION_COOKIE_NAME]["httponly"] = True
        cookie[SESSION_COOKIE_NAME]["samesite"] = "Lax"
        cookie[SESSION_COOKIE_NAME]["max-age"] = str(max(0, expires_at - now_ts()))
        if COOKIE_SECURE:
            cookie[SESSION_COOKIE_NAME]["secure"] = True
        return cookie.output(header="").strip()

    def build_expired_cookie(self):
        cookie = SimpleCookie()
        cookie[SESSION_COOKIE_NAME] = ""
        cookie[SESSION_COOKIE_NAME]["path"] = "/"
        cookie[SESSION_COOKIE_NAME]["httponly"] = True
        cookie[SESSION_COOKIE_NAME]["samesite"] = "Lax"
        cookie[SESSION_COOKIE_NAME]["max-age"] = "0"
        if COOKIE_SECURE:
            cookie[SESSION_COOKIE_NAME]["secure"] = True
        return cookie.output(header="").strip()

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as error:
            raise ValueError(f"Request body is not valid JSON: {error.msg}") from error

        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")

        return payload

    def send_json(self, status, payload, cookies=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type=None, cache_control="no-store"):
        content_type = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        message = "%s - - [%s] %s\n" % (
            self.address_string(),
            self.log_date_time_string(),
            format % args,
        )
        print(message, end="")


def main():
    server = ThreadingHTTPServer((HOST, PORT), ThreadReaderHandler)
    print(f"Thread reader server listening on http://{HOST}:{PORT}")
    print(f"Data directory: {DATA_DIR}")
    print(f"Users file: {USERS_FILE}")
    print(f"Invite codes file: {INVITE_CODES_FILE}")
    server.serve_forever()


if __name__ == "__main__":
    main()

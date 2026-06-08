import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR
ORIGINAL_PAGES_DIR = PROJECT_DIR / "original_pages"
MD_PAGES_DIR = PROJECT_DIR / "md_pages"
THREAD_META_FILENAME = "thread_meta.json"
CONCATE_PENDING_FILENAME = "concate_pending.json"
PAGE_FILE_RE = re.compile(r"page(\d+)\.json$", re.IGNORECASE)
POST_NO_RE = re.compile(r"^(?:No\.|#)(\d+)$", re.IGNORECASE)
SPLIT_OUTPUT = False
PER_FILE = 500
OUTPUT_SUFFIX = "txt"
ALLOWED_OUTPUT_SUFFIXES = {"md", "txt"}
REQUIRE_PENDING_MARKER = True


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def page_sort_key(path):
    match = PAGE_FILE_RE.search(path.name)
    if match:
        return int(match.group(1))
    return float("inf")


def get_post_number(post_no):
    match = POST_NO_RE.match(str(post_no).strip())
    if not match:
        return None
    return int(match.group(1))


def is_all_nines_post(post_no):
    number = get_post_number(post_no)
    if number is None:
        return False
    digits = str(number)
    return digits and set(digits) == {"9"}


def load_page_groups(pages_dir):
    page_groups = []
    seen_post_nos = set()

    page_files = sorted(pages_dir.glob("*.json"), key=page_sort_key)
    if not page_files:
        raise FileNotFoundError(f"{pages_dir} 下没有找到分页 json 文件。")

    for page_file in page_files:
        print(f"读取: {page_file}")
        page_posts = load_json(page_file)
        if not isinstance(page_posts, list):
            raise ValueError(f"{page_file} 顶层不是 list。")

        posts = []
        for post in page_posts:
            if not isinstance(post, dict):
                continue

            post_no = post.get("post_no")
            if not post_no:
                continue

            if is_all_nines_post(post_no):
                continue

            if post_no in seen_post_nos:
                continue

            seen_post_nos.add(post_no)
            posts.append(post)

        if posts:
            page_groups.append(
                {
                    "page_no": int(page_sort_key(page_file)),
                    "posts": posts,
                }
            )

    return page_groups


def load_thread_meta(thread_dir):
    meta_path = thread_dir / THREAD_META_FILENAME
    if not meta_path.is_file():
        return {}

    meta = load_json(meta_path)
    return meta if isinstance(meta, dict) else {}


def normalize_thread_title(thread_dir):
    meta = load_thread_meta(thread_dir)
    title = str(meta.get("title", "")).strip()
    if title:
        return title
    return thread_dir.name


def format_export_time(value=None):
    if value is None:
        current = datetime.now(timezone.utc)
    else:
        current = datetime.fromtimestamp(float(value), tz=timezone.utc)
    return current.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def get_export_time(thread_dir):
    meta = load_thread_meta(thread_dir)
    downloaded_at = meta.get("downloaded_at")
    try:
        if downloaded_at is not None and str(downloaded_at).strip() != "":
            return format_export_time(downloaded_at)
    except (TypeError, ValueError, OSError):
        pass
    return format_export_time()


def format_thread_number(post_no):
    number = get_post_number(post_no)
    if number is not None:
        return str(number)
    return str(post_no or "").replace("No.", "").replace("#", "").strip()


def format_post_title(post):
    title = str(post.get("title", "")).strip()
    return title or "无标题"


def escape_markdown_text(text):
    value = str(text or "")
    value = value.replace("\\", "\\\\")
    replacements = {
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "#": "\\#",
        "+": "\\+",
        # "-": "\\-",
        "!": "\\!",
        "|": "\\|",
        ">": "&gt;",
        "<": "&lt;",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def format_post_markdown(post, thread_dir):
    post_no = str(post.get("post_no", "")).strip()
    user_id = str(post.get("user_id", "")).strip()
    post_time = str(post.get("time", "")).strip()
    content = str(post.get("content", "")).strip()
    po = "PO主" if str(post.get("PO", "")).strip() else ""
    img_url = str(post.get("img_url", "")).strip()

    # content = content.replace("∀ﾟ", "∀ ﾟ")
    # content = content.replace("∇ﾟ", "∇ ﾟ")
    content = escape_markdown_text(content)

    lines = [f"### {format_post_title(post)}", ""]
    lines.append(f"ID: {post_no}  ")
    if post_time:
        lines.append(f"时间: {post_time}  ")
    lines.append("用户: 无名氏  ")
    if user_id:
        lines.append(f"用户ID: {user_id}  ")
    if po:
        lines.append(f"身份: {po}  ")
    lines.append("")
    if content:
        lines.append(content)

    if img_url:
        lines.extend(["", f"![Image]({img_url})"])

    lines.extend(["", "---"])
    return "\n".join(lines)


def clear_markdown_outputs(output_dir):
    if not output_dir.exists():
        return

    for output_path in output_dir.glob(f"*.{OUTPUT_SUFFIX}"):
        output_path.unlink()


def build_markdown_document(thread_dir, page_groups, total_pages, export_time):
    first_post_no = ""
    for group in page_groups:
        posts = group.get("posts", [])
        if posts:
            first_post_no = str(posts[0].get("post_no", "")).strip()
            break

    lines = [
        f"# 串号: {format_thread_number(first_post_no)}",
        "",
        f"导出时间: {export_time}",
        f"总页数: {total_pages}",
        "",
        "---",
        "",
    ]

    for group in page_groups:
        lines.append(f"## 第 {group['page_no']} 页")
        lines.append("")
        for post in group["posts"]:
            lines.append(format_post_markdown(post, thread_dir))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_parts(thread_dir, title, page_groups, per_file, split_output):
    total_pages = len(page_groups)
    if total_pages == 0:
        print(f"跳过空帖子: {thread_dir}")
        return []

    safe_title = str(title).strip() or thread_dir.name
    output_dir = MD_PAGES_DIR / safe_title
    output_dir.mkdir(parents=True, exist_ok=True)
    clear_markdown_outputs(output_dir)

    export_time = get_export_time(thread_dir)
    part_count = math.ceil(total_pages / per_file) if split_output else 1
    output_paths = []

    for part in range(part_count):
        if split_output:
            start = part * per_file
            end = min(start + per_file, total_pages)
        else:
            start = 0
            end = total_pages

        chunk = page_groups[start:end]
        body = build_markdown_document(thread_dir, chunk, total_pages, export_time)

        if split_output:
            output_path = output_dir / f"{safe_title}_part{part + 1}.{OUTPUT_SUFFIX}"
        else:
            output_path = output_dir / f"{safe_title}.{OUTPUT_SUFFIX}"

        output_path.write_text(body, encoding="utf-8")
        output_paths.append(output_path)
        print(f"已生成：{output_path}（第 {start + 1} 页 - 第 {end} 页）")

    return output_paths


def find_pending_threads():
    if not ORIGINAL_PAGES_DIR.exists():
        raise FileNotFoundError(f"未找到目录: {ORIGINAL_PAGES_DIR}")

    pending_threads = []
    for thread_dir in sorted(path for path in ORIGINAL_PAGES_DIR.iterdir() if path.is_dir()):
        if REQUIRE_PENDING_MARKER and not (thread_dir / CONCATE_PENDING_FILENAME).is_file():
            continue
        if not (thread_dir / "pages").is_dir():
            continue
        pending_threads.append(thread_dir)
    return pending_threads


def main():
    if OUTPUT_SUFFIX not in ALLOWED_OUTPUT_SUFFIXES:
        raise ValueError(f"OUTPUT_SUFFIX 只支持: {sorted(ALLOWED_OUTPUT_SUFFIXES)}")

    pending_threads = find_pending_threads()
    if not pending_threads:
        if REQUIRE_PENDING_MARKER:
            print(f"未找到带 {CONCATE_PENDING_FILENAME} 标记的帖子目录。")
        else:
            print("未找到可导出的帖子目录。")
        return

    for thread_dir in pending_threads:
        print(f"\n开始处理: {thread_dir}")
        title = normalize_thread_title(thread_dir)
        pages_dir = thread_dir / "pages"
        page_groups = load_page_groups(pages_dir)
        write_markdown_parts(thread_dir, title, page_groups, PER_FILE, SPLIT_OUTPUT)

    print("\nMarkdown 导出完成。")


if __name__ == "__main__":
    main()

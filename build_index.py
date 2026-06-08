import json
from pathlib import Path


# Server-side local configuration.
# This script is expected to live next to the HTML files.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INFO_FILENAME = "info.json"
OUTPUT_FILENAME = "index.json"


def load_info_file(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层不是对象。")

    return data


def normalize_record(record, info_path):
    normalized = dict(record)

    folder_name = info_path.parent.name
    normalized.setdefault("folder", folder_name)
    normalized.setdefault("title", folder_name)
    normalized.setdefault("tags", [])
    normalized.setdefault("series", "")
    normalized.setdefault("installment", None)
    normalized.setdefault("genre", "")
    normalized.setdefault("status", "")
    normalized.setdefault("po_user_id", "")
    normalized.setdefault("post_count", 0)
    normalized.setdefault("image_count", 0)
    normalized.setdefault("updated_at", "")

    return normalized


def record_sort_key(record):
    title = str(record.get("title", "")).strip()
    title_key = title.casefold()
    first_char = title_key[:1] if title_key else ""
    updated_at = str(record.get("updated_at", "")).strip()
    return (first_char, title_key, updated_at)


def build_index(data_dir):
    if not data_dir.exists():
        raise FileNotFoundError(f"未找到数据目录: {data_dir}")

    records = []
    seen_ids = set()
    info_files = sorted(data_dir.rglob(INFO_FILENAME))

    for info_path in info_files:
        if info_path.name != INFO_FILENAME:
            continue

        if info_path.parent == data_dir:
            continue

        print(f"读取: {info_path}")
        record = normalize_record(load_info_file(info_path), info_path)

        record_id = str(record.get("id", "")).strip()
        if not record_id:
            print(f"跳过缺少 id 的记录: {info_path}")
            continue

        if record_id in seen_ids:
            print(f"跳过重复 id: {record_id} | {info_path}")
            continue

        seen_ids.add(record_id)
        records.append(record)

    records.sort(key=record_sort_key)
    return records


def write_index(path, records):
    with path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def main():
    output_path = DATA_DIR / OUTPUT_FILENAME
    records = build_index(DATA_DIR)
    write_index(output_path, records)

    print("\n索引生成完成")
    print(f"记录数: {len(records)}")
    print(f"输出文件: {output_path}")


if __name__ == "__main__":
    main()

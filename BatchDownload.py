import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 选择下载器： "NMB" / "BOG" / "AWD"
DOWNLOADER = "AWD"

# 批量任务列表示例：
# {
# "thread_url": "50033943",  # 也可以写完整 URL
# "thread_title": "xx农业大学学生手册",
# "tags": [],
# "series": "其他",
# "installment": None,
# "genre": "规则怪谈",
# "status": "完结",
# },
# {
# "thread_url": "60955838",
# "thread_title": "全部通城际快递公司",
# "tags": [],
# "series": "其他",
# "installment": None,
# "genre": "规则怪谈",
# "status": "痛",
# }

TASKS = [
]



DOWNLOADER_MODULES = {
    "NMB": ROOT / "NMBGet.py",
    "BOG": ROOT / "BOGGet.py",
    "AWD": ROOT / "AWDGet.py",
}

BASE_URLS = {
    "NMB": "https://www.nmbxd1.com/t/{thread_id}",
    "BOG": "http://bog.ac/t/{thread_id}",
    "AWD": "https://aweidao1.com/t/{thread_id}",
}


def load_module(module_path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_thread_url(site_key, value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("thread_url 不能为空。")

    if text.isdigit():
        return BASE_URLS[site_key].format(thread_id=text)

    return text


def normalize_tags(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_task(site_key, task):
    if not isinstance(task, dict):
        raise TypeError(f"任务必须是 dict，实际是: {type(task)!r}")

    normalized = {
        "thread_url": normalize_thread_url(site_key, task.get("thread_url", "")),
        "thread_title": str(task.get("thread_title", "")).strip(),
        "tags": normalize_tags(task.get("tags", [])),
        "series": str(task.get("series", "")).strip(),
        "installment": task.get("installment"),
        "genre": str(task.get("genre", "")).strip(),
        "status": str(task.get("status", "")).strip(),
    }

    if not normalized["thread_title"]:
        raise ValueError(f"任务缺少 thread_title: {json.dumps(task, ensure_ascii=False)}")

    installment = normalized["installment"]
    if installment in ("", "null"):
        normalized["installment"] = None
    elif installment is not None and (
        isinstance(installment, bool) or not isinstance(installment, (int, float))
    ):
        raise ValueError(
            f"installment ????????????? None: {json.dumps(task, ensure_ascii=False)}"
        )

    return normalized


def configure_module(module, task):
    module.THREAD_URL = task["thread_url"]
    module.THREAD_TITLE = task["thread_title"]
    module.TAGS = task["tags"]
    module.SERIES = task["series"]
    module.INSTALLMENT = task["installment"]
    module.GENRE = task["genre"]
    module.STATUS = task["status"]

    headers = getattr(module, "HEADERS", None)
    session = getattr(module, "SESSION", None)
    if isinstance(headers, dict) and isinstance(session, object):
        if "referer" in headers:
            headers["referer"] = task["thread_url"]
        try:
            session.headers.update(headers)
        except Exception:
            pass


def main():
    site_key = str(DOWNLOADER or "").strip().upper()
    module_path = DOWNLOADER_MODULES.get(site_key)
    if module_path is None:
        raise ValueError(f"不支持的下载器: {DOWNLOADER}")
    if not module_path.exists():
        raise FileNotFoundError(f"未找到下载器文件: {module_path}")

    if not TASKS:
        print("TASKS 为空，没有可执行的任务。")
        return

    module = load_module(module_path, f"batch_downloader_{site_key.lower()}")
    run_download = getattr(module, "run_download", None)
    if not callable(run_download):
        raise RuntimeError(f"{module_path.name} 中未找到可调用的 run_download()")

    total = len(TASKS)
    for index, raw_task in enumerate(TASKS, start=1):
        task = normalize_task(site_key, raw_task)
        print(f"[{index}/{total}] 开始: {task['thread_title']} | {task['thread_url']}")
        configure_module(module, task)
        run_download()
        print(f"[{index}/{total}] 完成: {task['thread_title']}")

    print("全部任务执行完成。")


if __name__ == "__main__":
    main()

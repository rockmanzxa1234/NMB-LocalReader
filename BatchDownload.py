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
    {
        "thread_url": "44960716",
        "thread_title": "水手",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44879720",
        "thread_title": "淼沝公寓",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44932678",
        "thread_title": "小镇",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "规则怪谈",
        "status": "痛",
    },
    {
        "thread_url": "21444042",
        "thread_title": "迪士尼",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "35115284",
        "thread_title": "给新保姆的一些规定",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "40019975",
        "thread_title": "怪奇公寓",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45303777",
        "thread_title": "蠕虫之馆",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44970210",
        "thread_title": "动物园勘探(同人)",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45012429",
        "thread_title": "这里是安全屋",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45057077",
        "thread_title": "群友聊天准则",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "460315270",
        "thread_title": "牛之首",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "46111241",
        "thread_title": "湖城静丸：互联网与阴谋论",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45819575",
        "thread_title": "大无语，一觉醒来家没了",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45086946",
        "thread_title": "离校指南",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "46109517",
        "thread_title": "为了你的义务",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45180843",
        "thread_title": "白月光",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45112638",
        "thread_title": "C市政府关于规范化居民管理的通告",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45065672",
        "thread_title": "深夜水族店",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45067632",
        "thread_title": "我在我家小区！迷！路！了！",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44948666",
        "thread_title": "规矩好多幼儿园",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45152611",
        "thread_title": "学校的食堂变得怪怪的…",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44902043",
        "thread_title": "口口列车搭乘指南",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44995056",
        "thread_title": "观影人士行动指引及注意事项",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44941315",
        "thread_title": "如何当一名“子女”",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "50600577",
        "thread_title": "人类饲养手册",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "56767975",
        "thread_title": "宾客到",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "52998071",
        "thread_title": "月亮怪谈",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45787289",
        "thread_title": "YK学校守则",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "44971944",
        "thread_title": "欢迎来到口国人民口口大学",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "40075118",
        "thread_title": "咻咻俏皮的口哨声",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45594790",
        "thread_title": "自己怪谈",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "20231124",
        "thread_title": "客运车抛锚了",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
    {
        "thread_url": "45013556",
        "thread_title": "温馨小家短租公寓",
        "tags": [],
        "series": "其他",
        "installment": None,
        "genre": "",
        "status": "",
    },
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

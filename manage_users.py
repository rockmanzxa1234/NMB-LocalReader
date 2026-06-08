import json
import os
import hashlib
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "auth_users.json"

TARGET_USERNAME = "admin"
TARGET_PASSWORD = "admin"
TARGET_ENABLED = True
PBKDF2_ITERATIONS = 310000


def hash_password(password, iterations=PBKDF2_ITERATIONS):
    salt_hex = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt_hex}${digest}"


def load_users():
    if not USERS_FILE.exists():
        return {"users": []}

    with USERS_FILE.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("auth_users.json 顶层必须是对象。")

    users = payload.get("users", [])
    if not isinstance(users, list):
        raise ValueError("auth_users.json 中的 users 必须是数组。")

    payload["users"] = users
    return payload


def upsert_user(payload, username, password, enabled):
    users = payload["users"]
    username = str(username or "").strip()
    if not username:
        raise ValueError("TARGET_USERNAME 不能为空。")

    if not password:
        raise ValueError("TARGET_PASSWORD 不能为空。")

    hashed = hash_password(password)
    record = {
        "username": username,
        "password_hash": hashed,
        "enabled": bool(enabled),
    }

    for index, user in enumerate(users):
        if isinstance(user, dict) and str(user.get("username", "")).strip() == username:
            users[index] = record
            return "updated", record

    users.append(record)
    return "created", record


def save_users(payload):
    with USERS_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    payload = load_users()
    action, record = upsert_user(
        payload,
        TARGET_USERNAME,
        TARGET_PASSWORD,
        TARGET_ENABLED,
    )
    save_users(payload)

    print(f"{action}: {record['username']}")
    print(f"enabled: {record['enabled']}")
    print(f"users file: {USERS_FILE}")


if __name__ == "__main__":
    main()

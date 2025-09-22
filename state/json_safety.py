
from __future__ import annotations
import json

def read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def read_json_dict(path: str) -> dict:
    obj = read_json(path)
    return obj if isinstance(obj, dict) else {}

def read_json_list(path: str) -> list:
    obj = read_json(path)
    return obj if isinstance(obj, list) else []

def write_json(path: str, obj) -> None:
    import os, tempfile, fcntl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock_fd = os.open(path + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        dir_fd = os.open(os.path.dirname(path) or ".", os.O_DIRECTORY)
        try:
            with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(path), delete=False, encoding="utf-8") as tf:
                json.dump(obj, tf, ensure_ascii=False, separators=(",", ":"))
                tf.flush(); os.fsync(tf.fileno()); tmp = tf.name
            os.replace(tmp, path); os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN); os.close(lock_fd)

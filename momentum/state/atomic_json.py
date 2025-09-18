
from __future__ import annotations
import json, os, tempfile, fcntl

class AtomicJSONWriter:
    def __init__(self, path: str, schema_version: str | None = None):
        self.path = path
        self.schema_version = schema_version

    def write(self, data: dict) -> None:
        if self.schema_version:
            data = dict(data); data["_schema"] = self.schema_version
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        lock_fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            dir_fd = os.open(os.path.dirname(self.path) or ".", os.O_DIRECTORY)
            try:
                with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(self.path), delete=False, encoding="utf-8") as tf:
                    json.dump(data, tf, separators=(",", ":"), ensure_ascii=False)
                    tf.flush(); os.fsync(tf.fileno()); tmp = tf.name
                os.replace(tmp, self.path); os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN); os.close(lock_fd)

def read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

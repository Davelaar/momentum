
from __future__ import annotations
import json, os, tempfile, fcntl

class AtomicJSONWriter:
    """
    Safe writer for JSON state files:
      - write to temp file in same dir
      - fsync file and directory
      - atomic rename
      - advisory file lock *.lock to avoid concurrent writers
    Adds/maintains a top-level "_schema" field if provided.
    """
    def __init__(self, path: str, schema_version: str | None = None):
        self.path = path
        self.schema_version = schema_version

    def _lock_path(self) -> str:
        return self.path + ".lock"

    def write(self, data: dict) -> None:
        if self.schema_version:
            data = dict(data)
            data["_schema"] = self.schema_version

        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        lock_fd = os.open(self._lock_path(), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            dir_fd = os.open(os.path.dirname(self.path) or ".", os.O_DIRECTORY)
            try:
                with tempfile.NamedTemporaryFile("w", dir=os.path.dirname(self.path), delete=False, encoding="utf-8") as tf:
                    json.dump(data, tf, separators=(",", ":"), ensure_ascii=False)
                    tf.flush()
                    os.fsync(tf.fileno())
                    tmp_name = tf.name
                os.replace(tmp_name, self.path)   # atomic on same fs
                os.fsync(dir_fd)                  # persist rename
            finally:
                os.close(dir_fd)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

def read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

# --- Mini migrator ---
def migrate_if_needed(path: str, target_schema: str, migrate_fn):
    """
    If file has no schema or older schema, call migrate_fn(old_dict) -> new_dict
    and write it atomically with target_schema.
    """
    current = read_json(path)
    cur_schema = current.get("_schema")
    if cur_schema == target_schema:
        return False  # nothing to do
    new_obj = migrate_fn(current)
    AtomicJSONWriter(path, schema_version=target_schema).write(new_obj)
    return True

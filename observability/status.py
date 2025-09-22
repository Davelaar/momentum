
from __future__ import annotations
import json, os, time, re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any

FRESH_THRESHOLD_SEC = 15

@dataclass
class FileStatus:
    path: str
    exists: bool
    age_seconds: Optional[float]
    fresh: Optional[bool]
    note: str = ""

@dataclass
class JsonCountStatus:
    path: str
    exists: bool
    ok: bool
    count: int
    note: str = ""

def _file_status(path: str, fresh_threshold: int = FRESH_THRESHOLD_SEC) -> FileStatus:
    if not os.path.exists(path):
        return FileStatus(path, False, None, None, "absent")
    try:
        mtime = os.path.getmtime(path)
        age = time.time() - mtime
        fresh = age < fresh_threshold
        return FileStatus(path, True, age, fresh, "")
    except Exception as e:
        return FileStatus(path, True, None, None, f"stat-failed: {e}")

def _json_count(path: str, key: Optional[str] = None) -> JsonCountStatus:
    if not os.path.exists(path):
        return JsonCountStatus(path, False, False, 0, "absent")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if key is not None and isinstance(data, dict) and key in data and isinstance(data[key], list):
            cnt = len(data[key])
        elif isinstance(data, list):
            cnt = len(data)
        elif isinstance(data, dict):
            # heuristic: count top-level list-like values
            cnt = sum(len(v) for v in data.values() if isinstance(v, list))
        else:
            cnt = 0
        return JsonCountStatus(path, True, True, cnt, "")
    except Exception as e:
        return JsonCountStatus(path, True, False, 0, f"json-failed: {e}")

def tail_errors(log_path: str, max_lines: int = 50) -> Dict[str, Any]:
    res = {"path": log_path, "exists": os.path.exists(log_path), "error_lines": 0, "note": ""}
    if not res["exists"]:
        res["note"] = "absent"
        return res
    try:
        with open(log_path, "rb") as f:
            try:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                block = 4096
                data = b""
                while len(data.splitlines()) <= max_lines and size > 0:
                    read = min(block, size)
                    size -= read
                    f.seek(size)
                    data = f.read(read) + data
            except Exception:
                f.seek(0)
                data = f.read()
        text = data.decode("utf-8", errors="replace")
        err_lines = [ln for ln in text.splitlines() if re.search(r'\berr(or)?\b', ln, re.IGNORECASE)]
        res["error_lines"] = len(err_lines)
        return res
    except Exception as e:
        res["note"] = f"tail-failed: {e}"
        return res

def snapshot(app_path: str) -> Dict[str, Any]:
    var = os.path.join(app_path, "var")
    hb_v2 = _file_status(os.path.join(var, "public_ws_v2_hb.txt"))
    hb_v1 = _file_status(os.path.join(var, "public_ws_v1_hb.txt"))
    hb_pr = _file_status(os.path.join(var, "private_ws_hb.txt"))

    open_orders = _json_count(os.path.join(var, "open_orders_state.json"))
    positions   = _json_count(os.path.join(var, "positions.json"))
    own_trades  = _json_count(os.path.join(var, "own_trades_state.json"))

    janitor_tail = tail_errors(os.path.join(var, "janitor.log"), max_lines=50)

    return {
        "heartbeats": {
            "public_ws_v2": asdict(hb_v2),
            "public_ws_v1": asdict(hb_v1),
            "private_ws": asdict(hb_pr),
        },
        "states": {
            "open_orders": asdict(open_orders),
            "positions": asdict(positions),
            "own_trades": asdict(own_trades),
        },
        "janitor": janitor_tail,
        "ts": time.time(),
    }

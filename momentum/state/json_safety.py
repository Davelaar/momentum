
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

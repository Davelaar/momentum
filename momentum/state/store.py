# L1 INTERFACE — FROZEN
from __future__ import annotations
from typing import Optional, Dict, Any
from pathlib import Path
import json

VAR = Path(__file__).resolve().parent.parent / "var"
STATE_PATH = VAR / "state.json"
VAR.mkdir(parents=True, exist_ok=True)

def _load() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"orders": {}, "fills": {}, "positions": {}, "pnl": {}}
    return json.loads(STATE_PATH.read_text())

def _save(data: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(data, indent=2))

def upsert_order(order_id: str, payload: Dict[str, Any]) -> None:
    data = _load()
    data["orders"][order_id] = payload
    _save(data)

def upsert_fill(fill_id: str, payload: Dict[str, Any]) -> None:
    data = _load()
    data["fills"][fill_id] = payload
    _save(data)

def get_position(pair: str) -> Optional[Dict[str, Any]]:
    data = _load()
    return data["positions"].get(pair)

def pnl_summary() -> Dict[str, Any]:
    data = _load()
    return data.get("pnl", {})

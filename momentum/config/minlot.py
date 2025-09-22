
from __future__ import annotations
import json, os
from typing import Tuple, Optional

# Defaults (can be overridden per pair)
DEFAULTS = {
    "min_qty": 0.0001,   # BTC spot minimum example
    "lot_step": 1e-8,    # BTC lot step
}

def _load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def for_pair(app_path: str, pair: str) -> Tuple[float, float]:
    """Return (min_qty, lot_step) for a given pair, falling back to DEFAULTS.
    Tries var/minlot.json if present (simple mapping {pair: {min_qty, lot_step}}).
    Universe.json currently lacks these fields; hook is here for future use.
    """
    # 1) Check var/minlot.json (preferred override if you create it later)
    m = _load_json(os.path.join(app_path, "var", "minlot.json"))
    if isinstance(m, dict):
        entry = m.get(pair) or {}
        try:
            mq = float(entry.get("min_qty", DEFAULTS["min_qty"]))
            ls = float(entry.get("lot_step", DEFAULTS["lot_step"]))
            return mq, ls
        except Exception:
            pass

    # 2) Fallback: defaults
    return DEFAULTS["min_qty"], DEFAULTS["lot_step"]

def quantize_qty(qty: float, lot_step: float) -> float:
    # Avoid float drift by rounding to nearest step using integer math
    steps = round(qty / lot_step)
    return steps * lot_step

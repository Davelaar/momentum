"""
Lightweight helpers for the E2E dry-run script.
- Safe JSON/NDJSON writes
- Rounding using optional pair rules (price_decimals, qty_decimals)
- Basic env/.env_meanrev loading for a few keys
"""
from __future__ import annotations
import os, json, math, time, pathlib

APP = os.environ.get("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum"

def _load_json(path: str | pathlib.Path):
    p = pathlib.Path(path)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: str | pathlib.Path, obj):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def append_ndjson(path: str | pathlib.Path, obj):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def now_ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def load_pair_rules():
    # Optional: var/pair_rules.json with entries like { "BTC/USD": {"price_decimals":2,"qty_decimals":6, "min_notional":10.0} }
    rules = _load_json(pathlib.Path(APP) / "var" / "pair_rules.json")
    return rules or {}

def get_decimals(pair: str, rules: dict):
    d = rules.get(pair, {})
    price_dec = int(d.get("price_decimals", 2))
    qty_dec = int(d.get("qty_decimals", 6))
    return price_dec, qty_dec

def round_price(v: float, decimals: int) -> float:
    q = 10 ** decimals
    return math.floor(v * q + 0.5) / q

def round_qty(v: float, decimals: int) -> float:
    # floor to avoid exceeding qty after rounding
    q = 10 ** decimals
    return math.floor(v * q) / q

def load_env_meanrev():
    # Try environment first
    out = {
        "ENTRY_MAX_NOTIONAL": os.environ.get("ENTRY_MAX_NOTIONAL"),
        "DEFAULT_TIF": os.environ.get("DEFAULT_TIF", "GTC"),
        "DEFAULT_POST_ONLY": os.environ.get("DEFAULT_POST_ONLY", "1"),
        "JANITOR_CLOSE_ORDER_TYPE": os.environ.get("JANITOR_CLOSE_ORDER_TYPE", "stop-loss"),
        "JANITOR_CLOSE_TIF": os.environ.get("JANITOR_CLOSE_TIF", "GTC"),
        "BREAKEVEN_OFFSET_PCT": os.environ.get("BREAKEVEN_OFFSET_PCT", "0.0"),
    }
    # Optionally read .env_meanrev if present (simple parse: KEY=VALUE lines)
    env_path = pathlib.Path(APP) / ".env_meanrev"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if k and v and out.get(k) in (None, ""):
                    out[k] = v
    return out

def to_float(x, default=None):
    try:
        return float(x)
    except Exception:
        return default

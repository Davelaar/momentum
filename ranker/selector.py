# L1 INTERFACE — FROZEN
from __future__ import annotations
from typing import List, Dict, Any
from pathlib import Path
import json

from momentum.domain.types import OrderPlan, TPEntry

UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "var" / "universe.json"

def refresh_universe() -> None:
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    universe = sorted(list({ "BTC/USD", "ETH/USD", "SOL/USD" }))
    UNIVERSE_PATH.write_text(json.dumps({"pairs": universe}, indent=2))

def evaluate(pair: str) -> Dict[str, Any]:
    metrics = {
        "pair": pair,
        "spread_bps": 3.0,
        "fee_bps": 26.0,
        "slippage_bps": 5.0,
        "score": 1.0,
        "reasons": ["placeholder score = 1.0"],
    }
    return metrics

def top(n: int) -> List[str]:
    if not UNIVERSE_PATH.exists():
        refresh_universe()
    data = json.loads(UNIVERSE_PATH.read_text())
    pairs = data.get("pairs", [])
    return pairs[:n]

def build_order_plan(max_notional_usd: float) -> OrderPlan:
    best = top(1)[0]
    px = 100.0
    qty = max_notional_usd / px
    tp1 = TPEntry(price=px * 1.015, qty=qty * 0.4)
    tp2 = TPEntry(price=px * 1.020, qty=qty * 0.6)
    plan = OrderPlan(pair=best, side="buy", qty=qty, limit_price=px, tp_legs=[tp1, tp2], sl_price=px*0.99, tif="gtc", meta={"note":"placeholder plan"})
    return plan

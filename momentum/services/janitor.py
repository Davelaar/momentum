
import os
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

@dataclass
class Action:
    kind: str                 # 'close_position' | 'cancel_order'
    symbol: str               # e.g. 'BTC/USD'
    qty: float
    reason: str
    order_id: Optional[str] = None

class Janitor:
    """Stateless planner reading var/positions.json & var/open_orders.json and producing actions.

    Env:
      - APP (default '.'): base path containing var/
      - JANITOR_MAX_AGE_SEC (default 10800)
      - DANGLING_SELL_USD_THRESHOLD (default 0.01)
    """
    def __init__(self, app_path: Optional[str] = None):
        self.app_path = app_path or os.environ.get("APP", ".")
        self.max_age_sec = int(os.environ.get("JANITOR_MAX_AGE_SEC", "10800"))
        self.dangling_sell_usd_threshold = float(os.environ.get("DANGLING_SELL_USD_THRESHOLD", "0.01"))

    # ---- IO helpers -------------------------------------------------------
    def _var(self, rel: str) -> str:
        return os.path.join(self.app_path, "var", rel)

    def _read_json(self, rel: str, default):
        try:
            with open(self._var(rel), "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return default

    # ---- Planning ---------------------------------------------------------
    def plan(self, now_ts: Optional[int] = None) -> Dict[str, Any]:
        now_ts = int(now_ts or time.time())
        positions = self._read_json("positions.json", {})
        open_orders = self._read_json("open_orders.json", [])

        actions: List[Action] = []

        # Rule 1: Close aged positions
        for symbol, pos in positions.items():
            qty = float(pos.get("qty", 0.0))
            opened_at = pos.get("opened_at")
            if qty <= 0 or opened_at is None:
                continue
            age = now_ts - int(opened_at)
            if age >= self.max_age_sec:
                actions.append(Action(
                    kind="close_position",
                    symbol=symbol,
                    qty=qty,
                    reason=f"age {age}s >= MAX_AGE_SEC {self.max_age_sec}s"
                ))

        # Rule 2: Cancel dangling SELLs (no holdings or below threshold)
        for o in open_orders:
            if o.get("side") != "sell":
                continue
            symbol = o.get("symbol")
            order_id = o.get("order_id")
            qty = float(o.get("qty", 0.0))
            holdings = positions.get(symbol, {})
            held_qty = float(holdings.get("qty", 0.0))
            held_usd = float(holdings.get("usd", 0.0))
            if held_qty <= 0.0 or held_usd <= self.dangling_sell_usd_threshold:
                actions.append(Action(
                    kind="cancel_order",
                    symbol=symbol,
                    qty=qty,
                    reason=f"dangling SELL with holdings qty={held_qty} (usd={held_usd}) below threshold",
                    order_id=order_id
                ))

        return {
            "ts": now_ts,
            "actions": [asdict(a) for a in actions]
        }

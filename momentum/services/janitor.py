
from __future__ import annotations
import json, os, time
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

APP = os.environ.get("APP", "/var/www/vhosts/snapdiscounts.nl/momentum")
VAR = os.path.join(APP, "var")
LOG = os.path.join(VAR, "janitor.log")
ACTIONS_JSON = os.path.join(VAR, "janitor_actions.json")

MAX_AGE_SEC = int(float(os.environ.get("JANITOR_MAX_AGE_SEC", 3 * 60 * 60)))
INTERVAL_SEC = int(float(os.environ.get("JANITOR_INTERVAL_SEC", 60)))
MIN_HOLDINGS_USD = float(os.environ.get("JANITOR_MIN_HOLDINGS_USD", 2.0))
MIN_HOLDINGS_QTY = float(os.environ.get("JANITOR_MIN_HOLDINGS_QTY", 0.00001))

POSITIONS_PATH = os.path.join(VAR, "positions.json")
ORDERS_PATH = os.path.join(VAR, "orders.json")
PRICES_PATH = os.path.join(VAR, "prices.json")

def _log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")

def _read_json(path: str, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        _log(f"error reading {path}: {e}")
        return default

@dataclass
class Action:
    kind: str
    symbol: str
    qty: float
    reason: str
    order_id: Optional[str] = None

class Janitor:
    def __init__(self):
        self.now = time.time()
        self.actions: List[Action] = []
        os.makedirs(VAR, exist_ok=True)

    def _usd_value(self, symbol: str, qty: float, pos: Dict[str, Any]) -> Optional[float]:
        if isinstance(pos, dict) and "usd_value" in pos:
            return float(pos["usd_value"])
        prices = _read_json(PRICES_PATH, {})
        px = prices.get(symbol)
        if px is None:
            return None
        return float(px) * float(qty)

    def scan_positions(self) -> None:
        positions = _read_json(POSITIONS_PATH, {})
        for symbol, pos in positions.items():
            qty = float(pos.get("qty", 0.0))
            opened_at = float(pos.get("opened_at", 0.0))
            age = self.now - opened_at if opened_at else 0.0
            if qty <= 0:
                continue
            if opened_at and age >= MAX_AGE_SEC:
                self.actions.append(Action(
                    kind="close_position",
                    symbol=symbol,
                    qty=qty,
                    reason=f"age {int(age)}s >= MAX_AGE_SEC {MAX_AGE_SEC}s"
                ))

    def scan_orders(self) -> None:
        orders = _read_json(ORDERS_PATH, [])
        positions = _read_json(POSITIONS_PATH, {})
        for o in orders:
            try:
                if o.get("status") != "open":
                    continue
                if o.get("side") != "sell":
                    continue
                symbol = o.get("symbol")
                o_qty = float(o.get("order_qty", 0.0))
                pos = positions.get(symbol, {})
                pos_qty = float(pos.get("qty", 0.0))
                usd_val = self._usd_value(symbol, pos_qty, pos)
                too_small = (pos_qty <= MIN_HOLDINGS_QTY) or (usd_val is not None and usd_val <= MIN_HOLDINGS_USD)
                if too_small:
                    self.actions.append(Action(
                        kind="cancel_order",
                        symbol=symbol,
                        qty=o_qty,
                        order_id=str(o.get("order_id") or o.get("client_order_id") or ""),
                        reason=f"dangling SELL with holdings qty={pos_qty} (usd={usd_val}) below threshold"
                    ))
            except Exception as e:
                _log(f"error scanning order {o}: {e}")

    def run_once(self, dry_run: bool = True) -> List[Action]:
        self.now = time.time()
        self.actions.clear()
        self.scan_positions()
        self.scan_orders()
        data = [asdict(a) for a in self.actions]
        with open(ACTIONS_JSON, "w") as f:
            json.dump({"ts": int(self.now), "actions": data, "dry_run": dry_run}, f, indent=2)
        if not data:
            _log("scan: no actions")
            return []
        for a in self.actions:
            if dry_run:
                _log(f"DRY-RUN → {a.kind} {a.symbol} qty={a.qty} reason={a.reason}")
            else:
                _log(f"LIVE (noop in janitor): {a.kind} {a.symbol} qty={a.qty} reason={a.reason}")
        return self.actions

def main(dry_run: bool = True, loop: bool = False) -> None:
    j = Janitor()
    if not loop:
        j.run_once(dry_run=dry_run)
        return
    _log(f"janitor loop start (dry_run={dry_run}, interval={INTERVAL_SEC}s)")
    while True:
        try:
            j.run_once(dry_run=dry_run)
        except Exception as e:
            _log(f"fatal in run_once: {e}")
        time.sleep(INTERVAL_SEC)

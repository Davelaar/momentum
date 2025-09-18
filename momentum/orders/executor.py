
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional, Dict

APP = os.environ.get("APP", "/var/www/vhosts/snapdiscounts.nl/momentum")
VAR_DIR = os.path.join(APP, "var")
WS_PAYLOADS_PATH = os.path.join(VAR_DIR, "ws_payloads.json")
POSITIONS_PATH = os.path.join(VAR_DIR, "positions.json")

ENTRY_MAX_NOTIONAL = float(os.environ.get("ENTRY_MAX_NOTIONAL", "10"))
ONE_POSITION_ONLY = int(os.environ.get("ONE_POSITION_ONLY", "1"))


def _mk_cl_id(prefix: str = "mom6") -> str:
    # cl_ord_id: up to 18 ASCII chars; keep it short and unique-ish
    return f"{prefix}-{uuid4().hex[:10]}"[:18]


def uuid4():
    import uuid as _uuid
    return _uuid.uuid4()


@dataclass
class TPLeg:
    price: float
    qty: float
    limit_price: Optional[float] = None  # if set -> take-profit-limit; else take-profit


@dataclass
class BuildResult:
    entry: Dict
    stop_loss: Optional[Dict]
    take_profits: List[Dict]
    meta: Dict


class OrderExecutor:
    """
    Build Kraken WS v2 add_order payloads (dry-run).
    - Entry: limit order (absolute price).
    - SL: stop-loss or stop-loss-limit using `triggers` (no deprecated fields).
    - TP: multiple legs as separate orders (take-profit / take-profit-limit).
    Docs alignment: https://docs.kraken.com/api/docs/websocket-v2/add_order/
    """

    def __init__(self, symbol: str, side: str, qty: float, limit_price: float, time_in_force: str = "gtc",
                 post_only: bool = True, validate: bool = True, reference: str = "last"):
        self.symbol = symbol
        self.side = side.lower()
        assert self.side in ("buy", "sell"), "side must be buy|sell"
        self.qty = float(qty)
        self.limit_price = float(limit_price)
        self.time_in_force = time_in_force
        self.post_only = bool(int(post_only)) if isinstance(post_only, (int, str)) else bool(post_only)
        self.validate = bool(int(validate)) if isinstance(validate, (int, str)) else bool(validate)
        self.reference = reference  # 'last' or 'index'
        self._meta: Dict = {}

    # --- guards ---
    def _enforce_entry_notional(self):
        notional = self.qty * self.limit_price
        if notional > ENTRY_MAX_NOTIONAL:
            raise ValueError(f"ENTRY_MAX_NOTIONAL exceeded: {notional:.2f} > {ENTRY_MAX_NOTIONAL:.2f} USD")
        self._meta["entry_notional"] = notional

    def _enforce_one_position_only(self):
        if not ONE_POSITION_ONLY:
            return
        try:
            with open(POSITIONS_PATH, "r") as f:
                pos = json.load(f)
        except FileNotFoundError:
            pos = {}
        open_pos = pos.get(self.symbol.replace("/", ""), {}) or pos.get(self.symbol, {})
        if open_pos:
            raise ValueError(f"ONE_POSITION_ONLY=1 violation: existing position found for {self.symbol}")

    # --- builders ---
    def _build_entry(self) -> Dict:
        # limit entry only (absolute price)
        return {
            "method": "add_order",
            "params": {
                "order_type": "limit",
                "side": self.side,
                "order_qty": self.qty,
                "symbol": self.symbol,
                "limit_price": self.limit_price,
                "time_in_force": self.time_in_force,
                "post_only": self.post_only,
                # DO NOT include reduce_only / margin on spot
                "validate": self.validate,
                "cl_ord_id": _mk_cl_id("mom6e"),
                # "token": "<WS-TOKEN>",  # placeholder; not used in dry-run
            }
        }

    def _build_sl(self, sl: Optional[float], sl_limit: Optional[float]) -> Optional[Dict]:
        if sl is None:
            return None
        if sl_limit is not None:
            return {
                "method": "add_order",
                "params": {
                    "order_type": "stop-loss-limit",
                    "side": "sell" if self.side == "buy" else "buy",
                    "order_qty": self.qty,
                    "symbol": self.symbol,
                    "triggers": {
                        "reference": self.reference,
                        "price": float(sl),
                        "price_type": "static"
                    },
                    "limit_price": float(sl_limit),
                    "time_in_force": "gtc",
                    "validate": self.validate,
                    "cl_ord_id": _mk_cl_id("mom6s"),
                }
            }
        else:
            return {
                "method": "add_order",
                "params": {
                    "order_type": "stop-loss",
                    "side": "sell" if self.side == "buy" else "buy",
                    "order_qty": self.qty,
                    "symbol": self.symbol,
                    "triggers": {
                        "reference": self.reference,
                        "price": float(sl),
                        "price_type": "static"
                    },
                    "time_in_force": "gtc",
                    "validate": self.validate,
                    "cl_ord_id": _mk_cl_id("mom6s"),
                }
            }

    def _build_tp_leg(self, leg: TPLeg) -> Dict:
        if leg.limit_price is not None:
            order_type = "take-profit-limit"
            leg_limit = float(leg.limit_price)
        else:
            order_type = "take-profit"
            leg_limit = None

        params = {
            "order_type": order_type,
            "side": "sell" if self.side == "buy" else "buy",
            "order_qty": float(leg.qty),
            "symbol": self.symbol,
            "triggers": {
                "reference": self.reference,
                "price": float(leg.price),
                "price_type": "static"
            },
            "time_in_force": "gtc",
            "validate": self.validate,
            "cl_ord_id": _mk_cl_id("mom6t"),
        }
        if leg_limit is not None:
            params["limit_price"] = leg_limit
        return {"method": "add_order", "params": params}

    # public API
    def build(self, sl: Optional[float], sl_limit: Optional[float], tp_legs: List[TPLeg]):
        # guards
        self._enforce_entry_notional()
        self._enforce_one_position_only()

        # qty checks for TP split
        sum_tp = sum(max(0.0, float(l.qty)) for l in tp_legs)
        if sum_tp > self.qty + 1e-12:
            raise ValueError(f"Sum of TP legs ({sum_tp}) exceeds entry qty ({self.qty}).")

        entry = self._build_entry()
        sl_payload = self._build_sl(sl, sl_limit)
        tps = [self._build_tp_leg(l) for l in tp_legs]

        meta = {
            **getattr(self, "_meta", {}),
            "guards": {
                "ENTRY_MAX_NOTIONAL": ENTRY_MAX_NOTIONAL,
                "ONE_POSITION_ONLY": ONE_POSITION_ONLY,
            },
            "qty": self.qty,
            "symbol": self.symbol,
            "side": self.side,
            "limit_price": self.limit_price,
        }

        return dict(entry=entry, stop_loss=sl_payload, take_profits=tps, meta=meta)

    @staticmethod
    def dump_to_var(result, path: str = WS_PAYLOADS_PATH) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        return path

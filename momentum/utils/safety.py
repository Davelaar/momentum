
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class SafetyKnobs:
    entry_max_notional: float = 10.0
    one_position_only: int = 1
    abs_limit_required: int = 1

class SafetyViolation(Exception):
    pass

def enforce_entry_notional(symbol: str, side: str, qty: float, price: float | None, quote_ccy: str, knobs: SafetyKnobs):
    if price is None:
        # for market orders we can't pre-check notional precisely; allow but caller may set cash_order_qty instead
        return
    notional = qty * price
    if notional > knobs.entry_max_notional:
        raise SafetyViolation(f"ENTRY_MAX_NOTIONAL exceeded: {notional:.6f} {quote_ccy} > {knobs.entry_max_notional}")

def enforce_abs_limit(order_type: str, limit_price: float | None, knobs: SafetyKnobs):
    needs_limit = order_type in ("limit","stop-loss-limit","take-profit-limit","iceberg","trailing-stop-limit")
    if needs_limit and knobs.abs_limit_required and (limit_price is None):
        raise SafetyViolation(f"ABS_LIMIT_REQUIRED: order_type={order_type} must include explicit limit_price")

def enforce_one_position_only(symbol: str, enabled: int):
    # Placeholder hook. Integrate with your position tracker to block if symbol already has an open position.
    # For now this is advisory only.
    if enabled:
        return  # no-op here; implement in the executor layer

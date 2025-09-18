# L1 INTERFACE — FROZEN
from __future__ import annotations
from momentum.domain.types import OrderRef

def run_once() -> None:
    return None

def on_fill(order_ref: OrderRef) -> None:
    return None

def on_tp1_hit(position_ref: str) -> None:
    return None

def on_all_tp_filled(position_ref: str) -> None:
    return None

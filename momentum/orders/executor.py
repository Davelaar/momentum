# L1 INTERFACE — FROZEN
from __future__ import annotations
from typing import List, Optional
from momentum.domain.types import OrderRef

def place_entry(pair: str, side: str, qty: float, limit_price: float, tif: str, clid: Optional[str]) -> OrderRef:
    return OrderRef(order_id=f"entry:{pair}:{limit_price}", clid=clid)

def place_sl(position_ref: str, stop_price: float, tif: str, clid: Optional[str]) -> OrderRef:
    return OrderRef(order_id=f"sl:{position_ref}:{stop_price}", clid=clid)

def place_tp_legs(position_ref: str, legs: list, tif: str) -> list[OrderRef]:
    return [OrderRef(order_id=f"tp:{position_ref}:{i}", clid=None) for i,_ in enumerate(legs, start=1)]

def amend_sl(order_ref: OrderRef, new_price: float) -> OrderRef:
    return OrderRef(order_id=order_ref.order_id.split(':')[0] + f":amended:{new_price}", clid=order_ref.clid)

def cancel(order_ref: OrderRef) -> None:
    return None

def cancel_all(position_ref: str) -> None:
    return None

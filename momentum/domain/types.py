from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Literal, Dict, Any

Side = Literal["buy", "sell"]
TIF = Literal["gtc", "ioc", "gtd"]

@dataclass(frozen=True, slots=True)
class OrderRef:
    order_id: str
    clid: Optional[str] = None

@dataclass(frozen=True, slots=True)
class TPEntry:
    price: float
    qty: float

@dataclass(frozen=True, slots=True)
class OrderPlan:
    pair: str
    side: Side
    qty: float
    limit_price: float
    tp_legs: List[TPEntry] = field(default_factory=list)
    sl_price: Optional[float] = None
    tif: TIF = "gtc"
    meta: Dict[str, Any] = field(default_factory=dict)

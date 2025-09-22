
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

OrderSide = Literal["buy","sell"]
OrderType = Literal["limit","market","stop-loss","stop-loss-limit","take-profit","take-profit-limit","trailing-stop","trailing-stop-limit"]

class TakeProfitLeg(BaseModel):
    trigger_price: float
    limit_price: float | None = None  # optional for market-style TP
    pct_size: float = Field(1.0, description="Fraction of base qty for this TP leg (0..1).")

class Intent(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType = "limit"
    qty: float
    limit_price: float | None = None
    tif: Literal["gtc","gtd","ioc"] = "gtc"
    post_only: bool = False
    margin: bool = False
    reduce_only: bool = False
    cl_ord_id: str | None = None
    order_userref: int | None = None
    deadline_ms: int = 5000
    validate_only: bool = True  # map to WS 'validate'
    # OTO secondary (single) — we use SL most commonly
    oto_order_type: Literal["stop-loss","stop-loss-limit","take-profit","take-profit-limit","trailing-stop","trailing-stop-limit"] | None = None
    oto_trigger_price: float | None = None
    oto_limit_price: float | None = None
    # Standalone TP legs (non-OTO). Executor will place these as separate add_order calls.
    tps: List[TakeProfitLeg] = []
    gtd_expire_iso: str | None = None  # for TIF=gtd

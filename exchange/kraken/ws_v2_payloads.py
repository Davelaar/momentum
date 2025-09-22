
from __future__ import annotations
import time, uuid
from typing import Any, Dict, Optional, List
from pydantic import BaseModel
from momentum.models.intent import Intent, TakeProfitLeg
from momentum.utils.safety import SafetyKnobs, enforce_abs_limit, enforce_entry_notional, enforce_one_position_only

WS_ENDPOINT = "wss://ws-auth.kraken.com/v2"

class AddOrderMessage(BaseModel):
    method: str = "add_order"
    params: Dict[str, Any]
    req_id: Optional[int] = None

def _deadline_iso(ms_from_now: int) -> str:
    # Kraken expects RFC3339 with milliseconds
    t = time.time() + (ms_from_now / 1000.0)
    # Format with milliseconds and Z
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int((t % 1)*1000):03d}Z"

def _gen_cl_ord_id(prefix: str = "mom") -> str:
    # Short 16-char free text is fine within 18 chars
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

def build_primary_payload(intent: Intent, quote_ccy: str, knobs: SafetyKnobs, token_placeholder: str = "TOKEN") -> AddOrderMessage:
    # Safety: one-position guard (advisory placeholder)
    enforce_one_position_only(intent.symbol, 1 if knobs.one_position_only else 0)
    # Safety: absolute limit if required
    enforce_abs_limit(intent.order_type, intent.limit_price, knobs)
    # Safety: entry max notional (uses limit price if available)
    enforce_entry_notional(intent.symbol, intent.side, intent.qty, intent.limit_price, quote_ccy, knobs)

    params: Dict[str, Any] = {
        "order_type": intent.order_type,
        "side": intent.side,
        "order_qty": float(intent.qty),
        "symbol": intent.symbol,
        "time_in_force": intent.tif,
        "reduce_only": False,  # per project rules
        "margin": False,       # Spot only
        "stp_type": "cancel_newest",
        "deadline": _deadline_iso(intent.deadline_ms),
        "validate": bool(intent.validate_only),
        "token": token_placeholder,  # caller must inject real token
    }
    if intent.limit_price is not None:
        params["limit_price"] = float(intent.limit_price)
    if intent.post_only:
        params["post_only"] = True
    if intent.cl_ord_id:
        params["cl_ord_id"] = intent.cl_ord_id
    else:
        params["cl_ord_id"] = _gen_cl_ord_id()
    if intent.order_userref is not None:
        # mutually exclusive with cl_ord_id; keep cl_ord_id preference
        params.pop("cl_ord_id", None)
        params["order_userref"] = int(intent.order_userref)
    if intent.tif == "gtd" and intent.gtd_expire_iso:
        params["expire_time"] = intent.gtd_expire_iso

    # OTO secondary (optional)
    if intent.oto_order_type:
        cond: Dict[str, Any] = {"order_type": intent.oto_order_type}
        # For OTO, Kraken v2 uses trigger_price/limit_price fields (not nested 'triggers')
        if intent.oto_trigger_price is not None:
            cond["trigger_price"] = float(intent.oto_trigger_price)
        if intent.oto_order_type.endswith("-limit"):
            if intent.oto_limit_price is None:
                raise ValueError("OTO limit order requires oto_limit_price")
            cond["limit_price"] = float(intent.oto_limit_price)
        params["conditional"] = cond

    return AddOrderMessage(params=params)

def build_standalone_tp_messages(symbol: str, side: str, base_qty: float, tps: List[TakeProfitLeg], quote_ccy: str,
                                 knobs: SafetyKnobs, token_placeholder: str = "TOKEN") -> List[AddOrderMessage]:
    msgs: List[AddOrderMessage] = []
    for i, leg in enumerate(tps, start=1):
        qty_leg = round(base_qty * float(leg.pct_size), 12)
        params: Dict[str, Any] = {
            "order_type": "take-profit-limit" if leg.limit_price is not None else "take-profit",
            "side": side,
            "order_qty": qty_leg,
            "symbol": symbol,
            "time_in_force": "gtc",
            "reduce_only": False,
            "margin": False,
            "stp_type": "cancel_newest",
            "deadline": _deadline_iso(knobs.entry_max_notional and 5000 or 5000),
            "validate": True,
            "cl_ord_id": _gen_cl_ord_id(f"tp{i}"),
            "token": token_placeholder,
        }
        # Trigger object for top-level triggered orders
        params["triggers"] = {
            "reference": "last",
            "price": float(leg.trigger_price),
            "price_type": "static",
        }
        if leg.limit_price is not None:
            params["limit_price"] = float(leg.limit_price)
        msgs.append(AddOrderMessage(params=params))
    return msgs


import os
from typing import Dict, Any, List, Optional

# Minimal pair normalizer; for now we assume wsname format is already used (e.g., 'BTC/USD')
def normalize_pair(symbol: str) -> str:
    return symbol  # already 'BTC/USD'

class OrdersExecutor:
    """Translate Janitor actions to Kraken WS v2 payloads (add_order / cancel_order).

    Env knobs:
      - JANITOR_CLOSE_ORDER_TYPE: 'market' (default) or 'limit'
      - JANITOR_CLOSE_TIF: timeinforce for close (default 'ioc' for market)
      - JANITOR_CLOSE_LIMIT_PRICE: required if order type is 'limit' (absolute price, no relative offsets)
      - ORDER_USERREF_PREFIX: optional prefix for order_userref/cl_ord_id grouping (not set by default)
    Policy:
      - For emergency closes we default to MARKET IOC to ensure exit.
      - Absolute limit prices only when 'limit' is chosen.
    """
    def __init__(self):
        self.close_ordertype = os.environ.get("JANITOR_CLOSE_ORDER_TYPE", "market").lower()
        self.close_tif = os.environ.get("JANITOR_CLOSE_TIF", "ioc")
        self.close_limit = os.environ.get("JANITOR_CLOSE_LIMIT_PRICE")  # string or None
        self.userref_prefix = os.environ.get("ORDER_USERREF_PREFIX")  # optional

        if self.close_ordertype not in ("market", "limit"):
            self.close_ordertype = "market"

    def _base_order(self, pair: str) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "event": "add_order",
            "ordertype": self.close_ordertype,
            "pair": pair,
            "timeinforce": self.close_tif,
        }
        if self.userref_prefix:
            base["order_userref"] = f"{self.userref_prefix}:janitor"
        return base

    def build_from_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        payloads: List[Dict[str, Any]] = []
        cancels: List[Dict[str, Any]] = []

        for a in plan.get("actions", []):
            kind = a.get("kind")
            symbol = a.get("symbol")
            qty = float(a.get("qty", 0.0))
            pair = normalize_pair(symbol)

            if kind == "close_position":
                order = self._base_order(pair)
                order.update({
                    "side": "sell",
                    "volume": qty,
                })
                if self.close_ordertype == "limit":
                    if not self.close_limit:
                        raise ValueError("JANITOR_CLOSE_LIMIT_PRICE required for limit closes")
                    order["price"] = float(self.close_limit)
                payloads.append(order)

            elif kind == "cancel_order":
                txid = a.get("order_id")
                if not txid:
                    # if no order_id, we skip; can be enhanced later
                    continue
                cancels.append({
                    "event": "cancel_order",
                    "txid": [txid],
                })

        return {
            "add_order": payloads,
            "cancel_order": cancels,
        }

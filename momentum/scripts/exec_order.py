
from __future__ import annotations
import os, sys, json, argparse, time
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import List, Dict, Any, Optional, Tuple

from momentum.state.atomic_json import read_json
from momentum.config.minlot import for_pair as minlot_for_pair, quantize_qty

getcontext().prec = 28  # ample precision

def _clid(prefix: str = "mom6e") -> str:
    return f"{prefix}-{int(time.time()*1000)%100000000:x}"

def _qdec(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))

def _usd(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _parse_tp(tp_str: str, qty: float) -> List[Dict[str, float]]:
    if not tp_str:
        return []
    legs = []
    for part in str(tp_str).split(","):
        part = part.strip()
        if not part:
            continue
        # formats:
        #   25200@40%
        #   25300@60%:25290  (trigger @25300, limit 25290 -> take-profit-limit)
        trig_and_rest = part.split("@", 1)
        if len(trig_and_rest) != 2:
            continue
        trigger = Decimal(trig_and_rest[0])
        pct_and_maybe_limit = trig_and_rest[1]
        if ":" in pct_and_maybe_limit:
            pct_part, limit_part = pct_and_maybe_limit.split(":", 1)
            limit_price = Decimal(limit_part)
            order_type = "take-profit-limit"
        else:
            pct_part = pct_and_maybe_limit
            limit_price = None
            order_type = "take-profit"
        pct = Decimal(pct_part.strip().rstrip("%")) / Decimal(100)
        legs.append({
            "order_type": order_type,
            "trigger": trigger,
            "limit": limit_price,
            "portion": pct
        })
    # size legs
    out = []
    qty_dec = _qdec(qty)
    for leg in legs:
        leg_qty = (qty_dec * leg["portion"]).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        out.append({
            "order_type": leg["order_type"],
            "trigger": float(leg["trigger"]),
            "limit": float(leg["limit"]) if leg["limit"] is not None else None,
            "qty": float(leg_qty)
        })
    return out

def _write_to_var(app_path: str, payload: Any, guard: bool=False) -> str:
    out_dir = os.path.join(app_path, "var")
    os.makedirs(out_dir, exist_ok=True)
    outp = os.path.join(out_dir, "ws_payloads.json")
    mode = "w"
    with open(outp, mode, encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
        f.write("\n")
    print(f"[dry-run] wrote {'guard result' if guard else 'payloads'} to ./var/ws_payloads.json")
    return outp

def _load_positions(app_path: str, symbol: str) -> Decimal:
    try:
        state = read_json(os.path.join(app_path, "var", "positions.json")) or {}
        row = state.get(symbol) or {}
        nb = Decimal(str(row.get("net_base", 0)))
        return nb
    except Exception:
        return Decimal("0")

def _has_pending_entry(app_path: str, symbol: str) -> bool:
    try:
        state = read_json(os.path.join(app_path, "var", "open_orders_state.json")) or {}
    except Exception:
        return False
    # Support both list and dict formats
    if isinstance(state, list):
        it = state
    elif isinstance(state, dict):
        it = state.get("open") or state.get("orders") or state.values()
        if isinstance(it, dict):
            it = list(it.values())
    else:
        it = []
    for od in it:
        try:
            if (od.get("symbol") == symbol or od.get("pair") == symbol) and od.get("side") == "buy" and od.get("status","open") == "open":
                return True
        except Exception:
            continue
    return False

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--side", required=True, choices=["buy","sell"])
    ap.add_argument("--qty", required=True, type=float)
    ap.add_argument("--limit", required=True, type=float)
    ap.add_argument("--sl", required=True, type=float)
    ap.add_argument("--sl_limit", required=True, type=float)
    ap.add_argument("--tp", default="")
    ap.add_argument("--validate", type=int, default=1)
    ap.add_argument("--dry_run", type=int, default=1)
    ap.add_argument("--app", default=os.environ.get("APP") or "")
    args = ap.parse_args()

    app_path = args.app or os.environ.get("APP") or os.getcwd()

    # Load minlot
    min_qty, lot_step = minlot_for_pair(app_path, args.symbol)

    # Quantize qty first
    qty_q = quantize_qty(float(args.qty), float(lot_step))
    limit_dec = _qdec(args.limit)
    notional = _usd(_qdec(qty_q) * limit_dec)

    # Guards
    ENTRY_MAX = _usd(Decimal("10.00"))
    entry_ok = notional <= ENTRY_MAX

    # ONE_POSITION_ONLY
    nb = _load_positions(app_path, args.symbol)
    has_pos = (nb != 0)
    has_pending = _has_pending_entry(app_path, args.symbol)
    one_pos_ok = (not has_pos) and (not has_pending)

    if not entry_ok:
        obj = {"error":"entry_max_notional_exceeded","notional":float(notional),"max":float(ENTRY_MAX)}
        _write_to_var(app_path, obj, guard=True)
        return 0
    if not one_pos_ok:
        reason = "existing_position" if has_pos else "pending_entry"
        obj = {"error":"one_position_only_blocked","symbol":args.symbol,"reason":reason}
        _write_to_var(app_path, obj, guard=True)
        return 0

    # Build payloads
    entry = {
        "method":"add_order",
        "params":{
            "order_type":"limit",
            "side": args.side,
            "order_qty": float(qty_q),
            "symbol": args.symbol,
            "limit_price": float(args.limit),
            "time_in_force":"gtc",
            "post_only": True,
            "validate": bool(args.validate),
            "cl_ord_id": _clid("mom6e")
        }
    }
    stop_loss = {
        "method":"add_order",
        "params":{
            "order_type":"stop-loss-limit",
            "side":"sell" if args.side=="buy" else "buy",
            "order_qty": float(qty_q),
            "symbol": args.symbol,
            "triggers":{
                "reference":"last",
                "price": float(args.sl),
                "price_type":"static"
            },
            "time_in_force":"gtc",
            "validate": bool(args.validate),
            "cl_ord_id": _clid("mom6s"),
            "limit_price": float(args.sl_limit)
        }
    }
    tp_legs = _parse_tp(args.tp, qty_q)
    take_profits: List[Dict[str, Any]] = []
    for leg in tp_legs:
        common = {
            "method":"add_order",
            "params":{
                "order_type": leg["order_type"],
                "side":"sell" if args.side=="buy" else "buy",
                "order_qty": float(leg["qty"]),
                "symbol": args.symbol,
                "triggers":{
                    "reference":"last",
                    "price": float(leg["trigger"]),
                    "price_type":"static"
                },
                "time_in_force":"gtc",
                "validate": bool(args.validate),
                "cl_ord_id": _clid("mom6t")
            }
        }
        if leg["order_type"] == "take-profit-limit" and leg["limit"] is not None:
            common["params"]["limit_price"] = float(leg["limit"])
        take_profits.append(common)

    meta = {
        "entry_notional": float(notional),
        "guards": {
            "ENTRY_MAX_NOTIONAL": {"ok": bool(entry_ok), "computed": float(notional), "limit": float(ENTRY_MAX)},
            "ONE_POSITION_ONLY": {"ok": bool(one_pos_ok), "reason": None if one_pos_ok else ("existing_position" if has_pos else "pending_entry")}
        },
        "min_order": {
            "ok": qty_q >= min_qty,
            "min_qty": float(min_qty),
            "effective_qty": float(qty_q)
        },
        "qty": float(qty_q),
        "symbol": args.symbol,
        "side": args.side,
        "limit_price": float(args.limit),
    }

    result = {
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profits": take_profits,
        "meta": meta
    }

    _write_to_var(app_path, result, guard=False)
    return 0

if __name__ == "__main__":
    sys.exit(main())

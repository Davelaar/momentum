
from __future__ import annotations
import asyncio, json, time
from typing import Tuple, Dict, Any
from ..kraken.rest_client import KrakenREST
from ..state.atomic_json import AtomicJSONWriter, read_json

SCHEMA_OPEN_ORDERS = "open_orders_state/v1"
SCHEMA_POSITIONS   = "positions_state/v1"

def _normalize_open_orders(oo_result: dict) -> Dict[str, Any]:
    open_orders = oo_result.get("open", {})
    norm = {}
    for txid, od in open_orders.items():
        descr = od.get("descr", {})
        def f(x): 
            try: return float(x)
            except Exception: return 0.0
        norm[txid] = {
            "pair": descr.get("pair"),
            "type": descr.get("type"),
            "ordertype": descr.get("ordertype"),
            "price": f(descr.get("price", 0)),
            "price2": f(descr.get("price2", 0)),
            "vol": f(od.get("vol", 0)),
            "vol_exec": f(od.get("vol_exec", 0)),
            "status": od.get("status", "open"),
            "oflags": descr.get("oflags", ""),
            "time": od.get("opentm"),
            "userref": od.get("userref"),
            "cl_ord_id": od.get("cl_ord_id"),
        }
    return norm

async def _compute_positions(kraken: KrakenREST) -> Dict[str, Any]:
    balances = await kraken.balances()
    non_zero = {asset: float(amt) for asset, amt in balances.items() if float(amt) != 0.0}
    if not non_zero:
        return {"positions": {}, "asof": time.time()}
    asset_map = {}
    for asset in non_zero:
        a = asset.replace("Z", "").replace("X", "")
        if a == "USD":
            continue
        asset_map[asset] = f"{a}USD"
    tick = {}
    if asset_map:
        pairs_csv = ",".join(asset_map.values())
        try:
            tick = await kraken.ticker(pairs_csv)
        except Exception:
            tick = {}
    positions = {}
    for asset, qty in non_zero.items():
        a = asset.replace("Z", "").replace("X", "")
        if a == "USD":
            continue
        info = tick.get(f"{a}USD", {})
        try:
            ask = float(info.get("a", [0])[0])
            bid = float(info.get("b", [0])[0])
            mid = (ask + bid) / 2 if (ask and bid) else 0.0
        except Exception:
            mid = 0.0
        positions[a] = {"qty": qty, "mark_usd": mid, "value_usd": qty * mid}
    return {"positions": positions, "asof": time.time()}

def _diff_states(current: dict, target: dict) -> dict:
    diff = {"add": {}, "change": {}, "remove": []}
    for k, v in target.items():
        if k not in current:
            diff["add"][k] = v
        elif current[k] != v:
            diff["change"][k] = {"from": current[k], "to": v}
    for k in current.keys() - target.keys():
        diff["remove"].append(k)
    return diff

async def reconcile(app_path: str, dry_run: bool = True):
    var_dir = f"{app_path}/var"
    oo_path = f"{var_dir}/open_orders_state.json"
    pos_path = f"{var_dir}/positions.json"

    kraken = KrakenREST()
    try:
        oo_live = _normalize_open_orders(await kraken.open_orders())
        oo_current = read_json(oo_path)
        if isinstance(oo_current, dict) and "_schema" in oo_current:
            oo_current = {k: v for k, v in oo_current.items() if k != "_schema"}
        diff_oo = _diff_states(oo_current, oo_live)

        pos_live = await _compute_positions(kraken)
        pos_current = read_json(pos_path)
        if isinstance(pos_current, dict) and "_schema" in pos_current:
            pos_current = {k: v for k, v in pos_current.items() if k != "_schema"}
        diff_pos = _diff_states(pos_current, pos_live)

        if not dry_run:
            AtomicJSONWriter(oo_path, schema_version=SCHEMA_OPEN_ORDERS).write(oo_live)
            AtomicJSONWriter(pos_path, schema_version=SCHEMA_POSITIONS).write(pos_live)
        return diff_oo, diff_pos
    finally:
        await kraken.close()

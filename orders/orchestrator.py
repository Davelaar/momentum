
from __future__ import annotations
import time, os, json, asyncio
from dataclasses import dataclass
from typing import List, Dict, Optional
from ..state.atomic_json import AtomicJSONWriter, read_json
from .executor import AddOrderExecutor
import aiohttp

SCHEMA_EXEC_HISTORY = "exec_history/v1"
WS_AUTH_URL = "wss://ws-auth.kraken.com/v2"

@dataclass
class EntrySpec:
    pair: str
    side: str
    ordertype: str
    volume: float
    price: Optional[float] = None
    tif: str = "gtc"
    post_only: int = 0
    client_id: Optional[str] = None
    userref: Optional[int] = None

@dataclass
class TPLeg:
    ratio: float
    price: float
    client_id: Optional[str] = None

@dataclass
class SLSpec:
    price: float
    limit_price: Optional[float] = None
    client_id: Optional[str] = None

def _cid(base: str, suffix: str) -> str:
    return f"{base}-{suffix}"[:32]

def _hist_path(app: str) -> str:
    return f"{app}/var/exec_history.json"

def _seen_clid(app: str, clid: str) -> bool:
    hist = read_json(_hist_path(app))
    return isinstance(hist, dict) and clid in hist.get("seen", [])

def _mark_clid(app: str, clid: str) -> None:
    hist = read_json(_hist_path(app)) or {}
    if not isinstance(hist, dict):
        hist = {}
    seen = set(hist.get("seen", [])); seen.add(clid)
    AtomicJSONWriter(_hist_path(app), schema_version=SCHEMA_EXEC_HISTORY).write({"seen": sorted(seen)})

def build_oto_plan(entry: EntrySpec, tps: List[TPLeg], sl: Optional[SLSpec], be_offset: float | None) -> Dict:
    basecid = entry.client_id or f"oto-{int(time.time())}"
    legs: List[Dict] = []
    legs.append({
        "kind": "ENTRY",
        "params": {
            "pair": entry.pair, "side": entry.side, "ordertype": entry.ordertype,
            "volume": entry.volume, "price": entry.price, "tif": entry.tif,
            "post_only": entry.post_only, "cl_ord_id": _cid(basecid, "E")
        }
    })
    if sl:
        sl_params = {
            "pair": entry.pair,
            "side": "sell" if entry.side == "buy" else "buy",
            "ordertype": "stop-loss-limit" if sl.limit_price else "stop-loss",
            "volume": entry.volume,
            "tif": "gtc",
            "post_only": 0,
            "cl_ord_id": _cid(basecid, "SL"),
            "triggers": {"reference": "last", "price": float(sl.price), "price_type": "static"},
        }
        if sl.limit_price is not None:
            sl_params["limit_price"] = float(sl.limit_price)
        legs.append({"kind": "SL", "params": sl_params})
    filled = 0.0
    for i, tp in enumerate(tps, start=1):
        vol = round(entry.volume * tp.ratio, 10)
        filled += vol
        legs.append({
            "kind": "TP",
            "params": {
                "pair": entry.pair, "side": "sell" if entry.side == "buy" else "buy",
                "ordertype": "limit",
                "volume": vol, "price": tp.price, "tif": "gtc",
                "post_only": 1, "cl_ord_id": _cid(basecid, f"TP{i}")
            }
        })
    rem = round(entry.volume - filled, 10)
    if rem > 0:
        i = len([l for l in legs if l["kind"]=="TP"]) + 1
        last_price = tps[-1].price if tps else (entry.price or 0) * (1.02 if entry.side=="buy" else 0.98)
        legs.append({
            "kind": "TP",
            "params": {
                "pair": entry.pair, "side": "sell" if entry.side == "buy" else "buy",
                "ordertype": "limit",
                "volume": rem, "price": last_price, "tif": "gtc",
                "post_only": 1, "cl_ord_id": _cid(basecid, f"TP{i}")
            }
        })
    return {"base_cid": basecid, "legs": legs, "be_offset": be_offset}

async def execute_plan(app: str, plan: Dict, validate: int = 1) -> Dict:
    ex = AddOrderExecutor()
    try:
        results = []
        for leg in plan["legs"]:
            params = dict(leg["params"])
            clid = params.pop("cl_ord_id", None)
            triggers = params.pop("triggers", None)
            kw = params
            if clid: kw["client_id"] = clid
            if triggers: kw["extras"] = {"triggers": triggers}
            if clid and _seen_clid(app, clid):
                results.append({"skipped":"duplicate", "clid": clid, "kind": leg["kind"]})
                continue
            res = await ex.add_order(validate=validate, **kw)
            results.append({"clid": clid, "res": res, "kind": leg["kind"]})
            if res.get("status") == "ok" and clid:
                _mark_clid(app, clid)
        return {"status": "ok", "results": results}
    finally:
        await ex.close()

async def amend_sl_to_be(app: str, entry_price: float, be_offset: float, sl_clid: str, sl_volume: float) -> Dict:
    """
    WS v2 amend_order with loop to skip initial status frames.
    """
    # Acquire token
    token = os.getenv("KRAKEN_WS_TOKEN")
    if not token:
        from ..kraken.rest_client import KrakenREST
        async with aiohttp.ClientSession() as s:
            kr = KrakenREST(session=s)
            token = (await kr._post_private("GetWebSocketsToken", {}))["token"]

    new_trigger = float(entry_price + (be_offset or 0.0))
    req = {"method": "amend_order", "params": {
        "cl_ord_id": sl_clid,
        "order_qty": float(sl_volume),
        "trigger_price": new_trigger,
        "trigger_price_type": "static",
        "token": token,
    }, "req_id": int(time.time()*1000)}

    async with aiohttp.ClientSession() as sess:
        ws = await sess.ws_connect(WS_AUTH_URL, heartbeat=25)
        await ws.send_str(json.dumps(req, separators=(",", ":"), ensure_ascii=False))

        # Read frames until we see amend_order ack or timeout
        deadline = asyncio.get_event_loop().time() + 10.0
        ack_payload = None
        while asyncio.get_event_loop().time() < deadline:
            msg = await ws.receive(timeout=10.0)
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = json.loads(msg.data)
            if data.get("method") == "amend_order" or "result" in data or "success" in data:
                ack_payload = data
                break
        await ws.close()

    if ack_payload is None:
        return {"status": "error", "ack": {"error": "timeout waiting for amend_order ack"}, "new_trigger": new_trigger}

    ok = ack_payload.get("success") is True and "result" in ack_payload
    return {"status": "ok" if ok else "error", "ack": ack_payload, "new_trigger": new_trigger}

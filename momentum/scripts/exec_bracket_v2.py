#!/usr/bin/env python3
import os, json, hmac, time, base64, hashlib, asyncio, argparse, math
from datetime import datetime, timezone, timedelta
import aiohttp
import websockets
from typing import Dict, Any, List, Optional

API_URL = "https://api.kraken.com"
WS_AUTH_URL = "wss://ws-auth.kraken.com/v2"

# ---------- Helpers

def load_keys():
    key = os.environ.get("KRAKEN_KEY")
    sec = os.environ.get("KRAKEN_SECRET")
    if not key or not sec:
        raise SystemExit("Missing KRAKEN_KEY/SECRET in environment (.env)")
    return key, sec

def sign_kraken(path: str, data: Dict[str, str], secret_b64: str) -> str:
    postdata = "&".join(f"{k}={v}" for k, v in data.items())
    nonce = data.get("nonce", "")
    sha256 = hashlib.sha256((nonce + postdata).encode()).digest()
    msg = path.encode() + sha256
    mac = hmac.new(base64.b64decode(secret_b64), msg, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()

async def rest(session: aiohttp.ClientSession, method: str, path: str, data: Dict[str, str], key: str, sec: str):
    if method != "POST":
        raise ValueError("Only POST supported for private REST here")
    url = API_URL + path
    nonce = str(int(time.time() * 1000))
    data = {"nonce": nonce, **data}
    headers = {
        "API-Key": key,
        "API-Sign": sign_kraken(path, data, sec),
        "User-Agent": "momentum-bracket-v2/1.0"
    }
    async with session.post(url, data=data, headers=headers) as resp:
        js = await resp.json()
        return js

async def get_ws_token(session, key, sec):
    js = await rest(session, "POST", "/0/private/GetWebSocketsToken", {}, key, sec)
    if not js.get("result") or "token" not in js["result"]:
        raise RuntimeError(f"GetWebSocketsToken failed: {js}")
    return js["result"]["token"]

async def get_balances(session, key, sec) -> Dict[str, float]:
    js = await rest(session, "POST", "/0/private/Balance", {}, key, sec)
    if js.get("error"):
        raise RuntimeError(f"Balance error: {js}")
    res = js.get("result", {})
    return {k: float(v) for k, v in res.items()}

def rfc3339_deadline(offset_s: float = 5.0) -> str:
    ts = datetime.now(timezone.utc) + timedelta(seconds=offset_s)
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")

def round_up_to_step(q: float, lot_decimals: int) -> float:
    step = 10 ** (-lot_decimals)
    return math.ceil(q / step) * step

# ---------- Kraken WS v2 message builders

def build_add_order(symbol: str, side: str, qty: float, order_type: str, *, limit_price: Optional[float]=None,
                    tif: str="gtc", validate: bool=True, token: str="", cl_id: Optional[str]=None,
                    triggers: Optional[dict]=None, reduce_only: bool=False) -> dict:
    params = {
        "order_type": order_type,
        "side": side,
        "order_qty": float(qty),
        "symbol": symbol,
        "time_in_force": tif,
        "reduce_only": bool(reduce_only),
        "margin": False,
        "stp_type": "cancel_newest",
        "deadline": rfc3339_deadline(5.0),
        "validate": bool(validate),
        "token": token
    }
    if limit_price is not None:
        params["limit_price"] = float(limit_price)
    if triggers:
        params["triggers"] = triggers
    if cl_id:
        return {"method": "add_order", "params": params, "req_id": None, "cl_ord_id": cl_id}
    return {"method": "add_order", "params": params, "req_id": None}

def build_edit_order(order_id: str, *, limit_price: Optional[float]=None, triggers: Optional[dict]=None,
                     token: str="") -> dict:
    params = {
        "order_id": order_id,
        "deadline": rfc3339_deadline(5.0),
        "token": token
    }
    if limit_price is not None:
        params["limit_price"] = float(limit_price)
    if triggers:
        params["triggers"] = triggers
    return {"method": "edit_order", "params": params, "req_id": None}

def looks_like_final(msg: Any) -> bool:
    return isinstance(msg, dict) and ("success" in msg or "result" in msg or "error" in msg)

# ---------- Bracket flow

async def run(symbol: str, limit_price: float, validate: bool,
              tp_pcts: List[float], tp_sizes: List[float],
              sl_offset_pct: float, be_enable: bool, be_offset_pct: float,
              max_balance_pct: float, lot_decimals: int, ordermin: float):
    key, sec = load_keys()
    async with aiohttp.ClientSession() as session:
        token = await get_ws_token(session, key, sec)
        bals = await get_balances(session, key, sec)

    quote_ccy = symbol.split("/")[-1]
    free = float(bals.get(quote_ccy, 0.0))
    if free <= 0:
        raise SystemExit(f"No free {quote_ccy} balance")

    notional_cap = float(os.environ.get("ENTRY_MAX_NOTIONAL", "1e9"))
    budget = min(free * max_balance_pct, notional_cap)
    qty_target = budget / limit_price
    qty = max(qty_target, ordermin)
    qty = round_up_to_step(qty, lot_decimals)

    primary = build_add_order(symbol, "buy", qty, "limit",
                              limit_price=limit_price, tif="gtc",
                              validate=validate, token=token, reduce_only=False)

    out = {"sizing": {"free_quote": free, "budget": budget, "qty": qty},
           "sent": [], "received": []}

    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws:
        # Subscribe to executions to watch fills
        sub = {"method":"subscribe", "params":{"channel":"executions", "snap_orders":False, "snap_trades":False, "token": token}}
        await ws.send(json.dumps(sub))
        out["sent"].append(sub)
        out["received"].append(json.loads(await ws.recv()))

        # Send entry
        await ws.send(json.dumps(primary))
        out["sent"].append(primary)

        entry_order_id = None
        entry_avg_price = None
        tp_order_ids: List[str] = []
        sl_order_id = None
        tp1_done = False

        deadline = time.time() + 25.0
        while time.time() < deadline:
            raw = await ws.recv()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"raw": raw}
            out["received"].append(msg)
            if isinstance(msg, dict) and msg.get("channel") == "executions" and msg.get("type") == "update":
                for er in msg.get("data", []):
                    if er.get("method") == "add_order" and er.get("success") is True:
                        # ack, not useful
                        pass
                    if er.get("exec_type") in ("new","pending_new"):
                        entry_order_id = er.get("order_id", entry_order_id)
                    if er.get("exec_type") == "trade" and er.get("side") == "buy":
                        entry_order_id = er.get("order_id", entry_order_id)
                        entry_avg_price = er.get("avg_price") or er.get("last_price") or limit_price

                        # Place TPs if not yet placed
                        if not tp_order_ids and tp_pcts and tp_sizes:
                            remain = qty
                            tps = []
                            # compute sizes (percentages of total qty)
                            sizes = [max(0.0, float(s)/100.0) for s in tp_sizes]
                            if abs(sum(sizes) - 1.0) > 1e-6:
                                # Normalize to 1.0
                                ssum = sum(sizes) or 1.0
                                sizes = [s/ssum for s in sizes]
                            for tp_pct, sfrac in zip(tp_pcts, sizes):
                                q_part = max(ordermin, round_up_to_step(qty * sfrac, lot_decimals))
                                q_part = min(q_part, remain)
                                remain -= q_part
                                tp_price = entry_avg_price * (1.0 + tp_pct/100.0)
                                tps.append(build_add_order(symbol, "sell", q_part, "take-profit-limit",
                                                           limit_price=tp_price, tif="gtc",
                                                           validate=validate, token=token, reduce_only=True,
                                                           triggers={"reference":"last","price":float(tp_price),"price_type":"static"}))
                            # any dust remains -> add to last TP
                            if remain > 0 and tps:
                                tps[-1]["params"]["order_qty"] = float(tps[-1]["params"]["order_qty"] + remain)
                            # send TPs
                            for t in tps:
                                await ws.send(json.dumps(t))
                                out["sent"].append(t)
                            # we don't know IDs until subsequent exec updates

                        # Place SL if not yet
                        if sl_order_id is None and sl_offset_pct > 0:
                            sl_trigger = entry_avg_price * (1.0 - sl_offset_pct/100.0)
                            sl_limit   = sl_trigger * 0.999  # tiny buffer under trigger
                            sl = build_add_order(symbol, "sell", qty, "stop-loss-limit",
                                                 limit_price=sl_limit, tif="gtc",
                                                 validate=validate, token=token, reduce_only=True,
                                                 triggers={"reference":"last","price":float(sl_trigger),"price_type":"static"})
                            await ws.send(json.dumps(sl))
                            out["sent"].append(sl)

                    # capture IDs for TP/SL after their acks
                    if er.get("exec_type") in ("new","pending_new") and er.get("side") == "sell":
                        if er.get("order_type") in ("stop-loss","stop-loss-limit") and sl_order_id is None:
                            sl_order_id = er.get("order_id")
                        if er.get("order_type") in ("take-profit","take-profit-limit"):
                            if er.get("order_id") not in tp_order_ids:
                                tp_order_ids.append(er.get("order_id"))

                    # Break-even: if any TP trade fires, move SL
                    if be_enable and er.get("exec_type") == "trade" and er.get("side") == "sell":
                        if not tp1_done:
                            tp1_done = True
                            be_trigger = entry_avg_price * (1.0 + be_offset_pct/100.0)
                            be_limit   = be_trigger * 0.999
                            if sl_order_id:
                                edit = build_edit_order(sl_order_id,
                                                        limit_price=be_limit,
                                                        triggers={"reference":"last","price":float(be_trigger),"price_type":"static"},
                                                        token=token)
                                await ws.send(json.dumps(edit))
                                out["sent"].append(edit)

            # stop if we saw a full fill + sent children
            if entry_avg_price and (tp_order_ids or sl_order_id):
                # we gave enough time to place children; exit
                pass

        print(json.dumps(out, indent=2))

def parse_env_array(key: str, default: str) -> list:
    s = os.environ.get(key, default)
    if not s:
        return []
    return [float(x.strip()) for x in s.split(",") if x.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True, help="e.g., SNX/USD")
    ap.add_argument("--limit", type=float, required=True, help="entry limit price")
    ap.add_argument("--validate", type=int, default=1)
    ap.add_argument("--lot-decimals", type=int, default=int(os.environ.get("LOT_DECIMALS", "2")))
    ap.add_argument("--ordermin", type=float, default=float(os.environ.get("ORDERMIN", "1")))

    args = ap.parse_args()

    tp_pcts = parse_env_array("TP_PCTS", "0.9,1.4,2.1")
    tp_sizes = parse_env_array("TP_SIZES", "50,30,20")
    sl_offset_pct = float(os.environ.get("SL_OFFSET_PCT", "0.4"))
    be_enable = os.environ.get("BE_ENABLE", "1") == "1"
    be_offset_pct = float(os.environ.get("BE_OFFSET_PCT", "0.05"))
    max_balance_pct = float(os.environ.get("MAX_BALANCE_PCT", "0.98"))

    asyncio.run(run(
        symbol=args.symbol,
        limit_price=args.limit,
        validate=bool(args.validate),
        tp_pcts=tp_pcts,
        tp_sizes=tp_sizes,
        sl_offset_pct=sl_offset_pct,
        be_enable=be_enable,
        be_offset_pct=be_offset_pct,
        max_balance_pct=max_balance_pct,
        lot_decimals=args.lot_decimals,
        ordermin=args.ordermin
    ))

if __name__ == "__main__":
    main()

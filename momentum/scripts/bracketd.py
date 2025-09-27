#!/usr/bin/env python3
import os, json, time, math, asyncio, argparse, base64, hmac, hashlib, urllib.parse, random
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List

import aiohttp
import websockets

API_URL        = "https://api.kraken.com"
WS_PUBLIC_URL  = "wss://ws.kraken.com/v2"
WS_AUTH_URL    = "wss://ws-auth.kraken.com/v2"

ASSET_ALIASES = {
    "USD": ["ZUSD","USD"],
    "EUR": ["ZEUR","EUR"],
    "BTC": ["XXBT","XBT","BTC"],
    "ETH": ["XETH","ETH"],
}

# ----------------- helpers -----------------
def rfc3339_ms(offset_s: float = 5.0) -> str:
    ts = datetime.now(timezone.utc) + timedelta(seconds=offset_s)
    return ts.isoformat(timespec="milliseconds").replace("+00:00","Z")

def round_to(v: float, dp: int) -> float:
    return float(f"{v:.{dp}f}")

def round_up_step(v: float, dp: int) -> float:
    step = 10 ** (-dp)
    return math.ceil(v / step) * step

def round_down_step(v: float, dp: int) -> float:
    step = 10 ** (-dp)
    return math.floor(v / step) * step

def new_req_id() -> int:
    return (int(time.time() * 1000) % 1_000_000_000) + random.randint(1, 999)

# ----------------- REST: token / pair specs / ticker -----------------
async def get_ws_token(session: aiohttp.ClientSession, key: str, sec_b64: str) -> str:
    path = "/0/private/GetWebSocketsToken"
    nonce = str(int(time.time() * 1000))
    data  = {"nonce": nonce}
    post  = urllib.parse.urlencode(data)
    sha   = hashlib.sha256((nonce + post).encode()).digest()
    mac   = hmac.new(base64.b64decode(sec_b64), path.encode() + sha, hashlib.sha512)
    sig   = base64.b64encode(mac.digest()).decode()
    hdr   = {
        "API-Key": key, "API-Sign": sig,
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "User-Agent": "momentum/bracketd"
    }
    async with session.post(API_URL + path, data=data, headers=hdr, timeout=30) as r:
        js = await r.json()
        if js.get("error"):
            raise RuntimeError(f"GetWebSocketsToken error: {js['error']}")
        tok = js.get("result", {}).get("token")
        if not tok:
            raise RuntimeError("GetWebSocketsToken: no token")
        return tok

async def get_pair_specs(symbol: str) -> Tuple[int, int, float]:
    """return (price_decimals, lot_decimals, ordermin)"""
    pair = symbol.replace("/", "")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API_URL}/0/public/AssetPairs?pair={pair}", timeout=10) as r:
            js = await r.json()
    if js.get("error"):
        return (3, 2, 0.0)
    res = js.get("result") or {}
    info = next(iter(res.values()))
    price_dp = int(info.get("pair_decimals", 3))
    lot_dp   = int(info.get("lot_decimals", 2))
    try:
        ordermin = float(info.get("ordermin", "0"))
    except:
        ordermin = 0.0
    return price_dp, lot_dp, ordermin

async def get_public_ask(symbol: str) -> Optional[float]:
    pair = symbol.replace("/", "")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API_URL}/0/public/Ticker?pair={pair}", timeout=10) as r:
            js = await r.json()
    if js.get("error"): return None
    res = js.get("result") or {}
    if not res: return None
    a = next(iter(res.values())).get("a")
    try: return float(a[0]) if a else None
    except: return None

async def get_public_last(symbol: str) -> Optional[float]:
    pair = symbol.replace("/", "")
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{API_URL}/0/public/Ticker?pair={pair}", timeout=10) as r:
            js = await r.json()
    if js.get("error"): return None
    res = js.get("result") or {}
    if not res: return None
    c = next(iter(res.values())).get("c")
    try: return float(c[0]) if c else None
    except: return None

# ----------------- balances / open_orders -----------------
def resolve_free_key(keys: dict, asset_code: str) -> Optional[str]:
    candidates = [asset_code, "X"+asset_code] + ASSET_ALIASES.get(asset_code, [])
    for k in candidates:
        if k in keys: return k
    return None

async def ws_balances_snapshot(ws, token: str, timeout_s: float = 6.0) -> dict:
    """
    Returns {asset: {"available": float, "balance": float}}
    """
    await ws.send(json.dumps({"method":"subscribe","params":{"channel":"balances","token": token}}))
    end = time.time() + timeout_s
    out: Dict[str, Dict[str, float]] = {}
    while time.time() < end:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
        try: data = json.loads(raw)
        except: continue
        if data.get("channel") == "balances" and data.get("type") in ("snapshot","update"):
            for it in data.get("data", []):
                asset = it.get("asset")
                if not asset: continue
                avail = it.get("available", it.get("balance", 0.0))
                bal   = it.get("balance", avail)
                try:
                    out[asset] = {"available": float(avail), "balance": float(bal)}
                except:
                    out[asset] = {"available": 0.0, "balance": 0.0}
            if data.get("type") == "snapshot":
                break
    return out

async def ws_open_orders_snapshot(token: str, timeout_s: float = 6.0) -> List[dict]:
    out: List[dict] = []
    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"method":"subscribe","params":{"channel":"open_orders","token": token}}))
        end = time.time() + timeout_s
        while time.time() < end:
            try: raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
            except asyncio.TimeoutError: break
            try: data = json.loads(raw)
            except: continue
            if data.get("channel") == "open_orders" and data.get("type") in ("snapshot","update"):
                out.extend(data.get("data", []))
                if data.get("type") == "snapshot": break
    return out

async def cancel_all_sells_for_symbol(symbol: str, token: str) -> Dict[str, Any]:
    openos = await ws_open_orders_snapshot(token, timeout_s=6.0)
    target_ids = [o.get("order_id") for o in openos if o.get("symbol")==symbol and o.get("side")=="sell"]
    results: List[dict] = []
    for oid in target_ids:
        payload = {"method":"cancel_order","params":{"order_id": oid, "symbol": symbol, "deadline": rfc3339_ms(5.0), "token": token}}
        async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws:
            rid = new_req_id()
            payload["req_id"] = rid
            await ws.send(json.dumps(payload))
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8.0)
                results.append(json.loads(raw))
            except asyncio.TimeoutError:
                results.append({"method":"cancel_order","req_id":rid,"timeout":True})
    return {"cancelled": target_ids, "replies": results}

# ----------------- WS send + wait ack by req_id -----------------
async def ws_send_and_wait_add_order(ws, payload: dict, timeout_s: float = 12.0) -> Tuple[dict, Optional[str], list]:
    received = []
    rid = new_req_id()
    payload = json.loads(json.dumps(payload))
    payload["req_id"] = rid
    await ws.send(json.dumps(payload))
    end = time.time() + timeout_s
    order_id = None
    while time.time() < end:
        try: raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
        except asyncio.TimeoutError: break
        try: msg = json.loads(raw)
        except: continue
        received.append(msg)
        if msg.get("method") == "add_order" and msg.get("req_id") == rid:
            if msg.get("success"): order_id = (msg.get("result") or {}).get("order_id")
            break
    return payload, order_id, received

# ----------------- fill watch -----------------
async def wait_for_fill(entry_id: str, symbol: str, qty: float, token: str, timeout_s: int = 300) -> Tuple[bool, float]:
    start = time.time()
    filled = 0.0
    sub_exec = {"method": "subscribe", "params": {"channel": "executions", "token": token}}
    sub_open = {"method": "subscribe", "params": {"channel": "open_orders", "token": token}}
    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps(sub_exec))
        await ws.send(json.dumps(sub_open))
        while time.time() - start < timeout_s:
            try: raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except asyncio.TimeoutError: continue
            try: data = json.loads(raw)
            except: continue

            if data.get("channel") == "executions" and data.get("type") in ("snapshot","update"):
                for it in data.get("data", []):
                    if it.get("order_id") == entry_id and it.get("symbol") == symbol:
                        try:
                            filled += float(it.get("qty", 0.0))
                        except:
                            pass
                        if filled + 1e-12 >= qty:
                            return True, filled

            if data.get("channel") == "open_orders":
                for it in data.get("data", []):
                    if it.get("order_id") == entry_id:
                        status = it.get("order_status") or it.get("status")
                        cum    = float(it.get("cum_qty", 0.0)) if it.get("cum_qty") else None
                        if status in ("closed","cancelled") and (cum is not None):
                            return (cum + 1e-12 >= qty), (cum if cum is not None else filled)
    return False, filled

# ----------------- public ticker watcher -----------------
async def ws_ticker_reaches(symbol: str, trigger_px: float, max_secs: int) -> bool:
    sub = {"method": "subscribe", "params": {"channel": "ticker", "symbol": [symbol]}}
    start = time.time()
    async with websockets.connect(WS_PUBLIC_URL, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps(sub))
        while time.time() - start < max_secs:
            try: raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            except asyncio.TimeoutError: continue
            try: data = json.loads(raw)
            except: continue
            if data.get("channel") == "ticker" and data.get("type") in ("snapshot","update"):
                for it in data.get("data", []):
                    px = None
                    if "last" in it:
                        try: px = float(it["last"])
                        except: pass
                    if px is None and "ask" in it:
                        try: px = float(it["ask"])
                        except: pass
                    if px is not None and px + 1e-12 >= trigger_px:
                        return True
    return False

# ----------------- reconcile: cancel sells → plaats 1 SL voor hele *vrije* positie -----------------
async def reconcile_existing(symbol: str, price_dp: int, lot_dp: int, ordermin: float, token: str) -> Dict[str, Any]:
    base, _ = symbol.split("/")
    out: Dict[str, Any] = {"symbol": symbol, "reconcile": {"base_available": 0.0, "base_balance": 0.0, "did_cancel": False, "action": None}}

    if os.getenv("RECONCILE_CANCEL_SELLS", "1") in ("1","true","True","yes","on"):
        cancel_info = await cancel_all_sells_for_symbol(symbol, token)
        out["reconcile"]["did_cancel"] = True
        out["reconcile"]["cancel"] = cancel_info
        await asyncio.sleep(0.8)  # reservering laten vrijvallen

    # balances snapshot (na evt. cancel)
    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws:
        bals = await ws_balances_snapshot(ws, token, timeout_s=6.0)

    key = resolve_free_key(bals, base)
    if not key:
        return out
    base_avail = float(bals[key].get("available", 0.0))
    base_total = float(bals[key].get("balance", base_avail))
    out["reconcile"]["balance_key"] = key
    out["reconcile"]["base_available"] = base_avail
    out["reconcile"]["base_balance"]   = base_total

    # qty op veilig: ε eraf en floorden op lot_dp
    eps = 1e-8
    qty = max(0.0, base_avail - eps)
    qty = round_down_step(qty, lot_dp)
    if qty <= 0.0 or (ordermin > 0 and qty + 1e-12 < ordermin):
        return out  # te klein om SL te plaatsen

    last = await get_public_last(symbol)
    if last is None:
        return out

    SL_PCT  = float(os.getenv("SL_PCT", "0.01"))
    BUF_PCT = float(os.getenv("PRICE_BUFFER_PCT", "0.001"))
    sl_trig = round_to(last * (1 - SL_PCT), price_dp)
    sl_lim  = round_to(sl_trig * (1 - BUF_PCT), price_dp)

    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws2:
        sl_payload = {
            "method":"add_order",
            "params":{
                "order_type":"stop-loss-limit","side":"sell",
                "order_qty": float(qty), "symbol": symbol,
                "time_in_force":"gtc","margin": False,"stp_type":"cancel_newest",
                "deadline": rfc3339_ms(5.0),
                "validate": False,
                "limit_price": sl_lim,
                "triggers": {"reference":"last","price": sl_trig,"price_type":"static"},
                "token": token
            }
        }
        sent_sl, sl_id, rec_sl = await ws_send_and_wait_add_order(ws2, sl_payload, timeout_s=12.0)
        out["reconcile"]["action"] = {"sl_sent": sent_sl, "sl_received": rec_sl, "sl_id": sl_id}

    return out

# ----------------- main flow: entry → fill → SL → (BE/TP via OCO-emulatie) -----------------
async def run(symbol: str, limit_price: float, validate: bool, use_ask: bool, reconcile: bool, reconcile_only: bool):
    key, sec = os.getenv("KRAKEN_KEY"), os.getenv("KRAKEN_SECRET")
    if not key or not sec:
        return {"error": "Missing KRAKEN_KEY/SECRET"}

    # precisie + ordermin
    if os.getenv("PRICE_DECIMALS") and os.getenv("LOT_DECIMALS"):
        price_dp, lot_dp = int(os.getenv("PRICE_DECIMALS")), int(os.getenv("LOT_DECIMALS"))
        # ordermin alsnog ophalen
        _, _, ordermin = await get_pair_specs(symbol)
    else:
        price_dp, lot_dp, ordermin = await get_pair_specs(symbol)

    # exits-config
    TP_PCT   = float(os.getenv("TP_PCT", "0.02"))
    SL_PCT   = float(os.getenv("SL_PCT", "0.01"))
    BUF_PCT  = float(os.getenv("PRICE_BUFFER_PCT", "0.001"))
    BE_EN    = os.getenv("BE_ENABLE", "1") in ("1","true","True","yes","on")
    BE_TRIG  = float(os.getenv("BE_TRIGGER_PCT", "0.01"))
    BE_OFF   = float(os.getenv("BE_OFFSET_PCT", "0.0005"))
    BE_WAIT  = int(os.getenv("BE_WATCH_SECS", "180"))

    out: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "result": {
            "price_dp": price_dp, "lot_dp": lot_dp,
            "reconcile": None,
            "limit": None, "sizing": None,
            "entry": {"sent": None, "received": [], "order_id": None},
            "filled": {"ok": None, "qty": 0.0},
            "sl": {"sent": None, "received": [], "order_id": None},
            "be": {"enabled": BE_EN, "trigger": None, "amend_sent": None, "amend_received": []},
            "tp": {"armed": True, "trigger": None, "placed": None}
        }
    }

    # token
    async with aiohttp.ClientSession() as session:
        token = await get_ws_token(session, key, sec)

    # 0) Reconcile (optioneel): cancel sells → zet 1 SL
    if reconcile:
        out["result"]["reconcile"] = await reconcile_existing(symbol, price_dp, lot_dp, ordermin, token)
        if reconcile_only:
            return out

    # 1) Entry sizing
    if use_ask:
        ask = await get_public_ask(symbol)
        if ask:
            limit_price = ask * 1.002
    limit_price = round_to(limit_price, price_dp)
    out["result"]["limit"] = limit_price

    max_pct   = float(os.getenv("MAX_BALANCE_PCT", "0.98"))
    entry_cap = float(os.getenv("ENTRY_MAX_NOTIONAL", "1e9"))

    # 2) Place entry (validate possible)
    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws:
        bals_map = await ws_balances_snapshot(ws, token, timeout_s=6.0)
        quote = symbol.split("/")[-1]
        qkey = resolve_free_key(bals_map, quote)
        free_quote = float(bals_map.get(qkey, {}).get("available", 0.0)) if qkey else 0.0
        if free_quote <= 0.0:
            out["result"]["error"] = f"no free {quote} balance"
            return out
        budget = min(free_quote * max_pct, entry_cap)

        qty = max(0.0, budget / limit_price)
        # primair naar beneden afronden zodat we nooit over budget gaan
        qty = round_down_step(qty, lot_dp)

        # ordermin check: indien te klein → probeer op te hogen naar ordermin
        if ordermin > 0 and qty + 1e-12 < ordermin:
            need_notional = ordermin * limit_price
            if need_notional <= budget + 1e-12:
                qty = round_up_step(ordermin, lot_dp)
            else:
                out["result"]["sizing"] = {"free": free_quote, "budget": budget, "qty": qty, "ordermin": ordermin}
                out["result"]["error"] = f"qty {qty} < ordermin {ordermin}"
                return out

        out["result"]["sizing"] = {"free": free_quote, "budget": budget, "qty": qty}

        entry_payload = {
            "method":"add_order",
            "params":{
                "order_type":"limit","side":"buy","order_qty": float(qty),"symbol": symbol,
                "time_in_force":"gtc","margin": False,"stp_type":"cancel_newest",
                "deadline": rfc3339_ms(5.0),
                "validate": bool(validate),
                "limit_price": float(limit_price),"token": token
            }
        }
        sent, entry_id, recvd = await ws_send_and_wait_add_order(ws, entry_payload, timeout_s=12.0)
        out["result"]["entry"]["sent"] = sent
        out["result"]["entry"]["received"].extend(recvd)
        out["result"]["entry"]["order_id"] = entry_id

    if validate:
        return out

    # 3) Wait for fill
    if not out["result"]["entry"]["order_id"]:
        out["result"]["error"] = "no entry order_id (live)"
        return out
    filled_ok, filled_qty = await wait_for_fill(out["result"]["entry"]["order_id"], symbol, out["result"]["sizing"]["qty"], token, timeout_s=300)
    out["result"]["filled"] = {"ok": filled_ok, "qty": filled_qty}
    if not filled_ok or filled_qty <= 0:
        out["result"]["error"] = "entry not fully filled within timeout"
        return out

    # 4) After fill: place ONLY SL (spot)
    sl_trig = round_to(limit_price * (1 - SL_PCT), price_dp)
    sl_lim  = round_to(sl_trig     * (1 - BUF_PCT), price_dp)
    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws2:
        sl_payload = {
            "method":"add_order",
            "params":{
                "order_type":"stop-loss-limit","side":"sell",
                "order_qty": float(filled_qty), "symbol": symbol,
                "time_in_force":"gtc","margin": False,"stp_type":"cancel_newest",
                "deadline": rfc3339_ms(5.0),
                "validate": False,
                "limit_price": sl_lim,
                "triggers": {"reference":"last","price": sl_trig,"price_type":"static"},
                "token": token
            }
        }
        sent_sl, sl_id, rec_sl = await ws_send_and_wait_add_order(ws2, sl_payload, timeout_s=12.0)
        out["result"]["sl"]["sent"] = sent_sl
        out["result"]["sl"]["received"].extend(rec_sl)
        out["result"]["sl"]["order_id"] = sl_id

    if not out["result"]["sl"]["order_id"]:
        out["result"]["error"] = "failed to place SL"
        return out

    # 5) OCO-emulatie: BE & TP
    tp_trig = round_to(limit_price * (1 + TP_PCT), price_dp)
    out["result"]["tp"]["trigger"] = tp_trig
    if BE_EN:
        out["result"]["be"]["trigger"] = round_to(limit_price * (1 + BE_TRIG), price_dp)

    async def maybe_move_to_break_even():
        if not BE_EN: return None
        hit = await ws_ticker_reaches(symbol, out["result"]["be"]["trigger"], BE_WAIT)
        if not hit: return {"be_hit": False}
        be_trig = round_to(limit_price * (1 + BE_OFF), price_dp)
        be_lim  = round_to(be_trig * (1 - BUF_PCT),  price_dp)
        # amend via ws-auth
        amend = {
            "method":"amend_order",
            "params":{
                "order_id": out["result"]["sl"]["order_id"],
                "symbol": symbol,
                "deadline": rfc3339_ms(5.0),
                "trigger_price": be_trig,
                "trigger_price_type": "static",
                "limit_price": be_lim,
                "token": None
            }
        }
        async with aiohttp.ClientSession() as s:
            tok = await get_ws_token(s, os.getenv("KRAKEN_KEY"), os.getenv("KRAKEN_SECRET"))
        amend["params"]["token"] = tok
        async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws3:
            await ws3.send(json.dumps(amend))
            try:
                r = await asyncio.wait_for(ws3.recv(), timeout=8.0)
                return {"be_hit": True, "amend_sent": amend, "amend_reply": json.loads(r)}
            except asyncio.TimeoutError:
                return {"be_hit": True, "amend_sent": amend, "amend_reply": {"error":"ws-reply-timeout"}}

    async def maybe_flip_to_take_profit():
        hit = await ws_ticker_reaches(symbol, tp_trig, BE_WAIT)
        if not hit: return {"tp_hit": False}
        # cancel SL
        async with aiohttp.ClientSession() as s:
            tok = await get_ws_token(s, os.getenv("KRAKEN_KEY"), os.getenv("KRAKEN_SECRET"))
        cancel = {"method":"cancel_order","params":{"order_id": out["result"]["sl"]["order_id"], "symbol": symbol, "deadline": rfc3339_ms(5.0), "token": tok}}
        async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws4:
            await ws4.send(json.dumps(cancel))
            try: _ = await asyncio.wait_for(ws4.recv(), timeout=8.0)
            except asyncio.TimeoutError: pass

        # plaats TP-limit
        tp_px  = round_to(tp_trig * (1 - BUF_PCT), price_dp)
        tp_qty = float(out["result"]["filled"]["qty"])
        tp_payload = {
            "method":"add_order",
            "params":{
                "order_type":"limit","side":"sell",
                "order_qty": tp_qty, "symbol": symbol,
                "time_in_force":"gtc","margin": False,"stp_type":"cancel_newest",
                "deadline": rfc3339_ms(5.0),
                "validate": False,
                "limit_price": tp_px,
                "token": tok
            }
        }
        async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws5:
            sent_tp, tp_id, rec_tp = await ws_send_and_wait_add_order(ws5, tp_payload, timeout_s=12.0)
            return {"tp_hit": True, "tp_sent": sent_tp, "tp_received": rec_tp, "tp_id": tp_id}

    be_task = asyncio.create_task(maybe_move_to_break_even()) if BE_EN else None
    tp_task = asyncio.create_task(maybe_flip_to_take_profit())
    be_res  = await be_task if be_task else None
    tp_res  = await tp_task

    if be_res: out["result"]["be"].update(be_res)
    if tp_res: out["result"]["tp"]["placed"] = tp_res

    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--limit", type=float, required=True, help="Max price cap; met --use-ask 1 wordt limit ≈ ask*1.002.")
    ap.add_argument("--use-ask", type=int, default=1, help="1 = limit ≈ ask*1.002 + afronding")
    ap.add_argument("--validate", type=int, default=1, help="1 = alleen entry valideren; 0 = live (wacht op fill → SL → OCO-emulatie)")
    ap.add_argument("--reconcile", type=int, default=1, help="1 = bij start: cancel SELLs en zet 1 SL voor vrije positie")
    ap.add_argument("--reconcile-only", type=int, default=0, help="1 = alleen reconcile uitvoeren (geen entry)")
    args = ap.parse_args()

    print(json.dumps(asyncio.run(
        run(args.symbol, args.limit, bool(args.validate), bool(args.use_ask), bool(args.reconcile), bool(args.reconcile_only))
    ), indent=2))

if __name__ == "__main__":
    main()

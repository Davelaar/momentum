#!/usr/bin/env python3
import os, json, asyncio, aiohttp, time, math, base64, hmac, hashlib, urllib.parse
from typing import Dict, Any, Tuple, Optional, List

API = "https://api.kraken.com"
WS_AUTH = "wss://ws-auth.kraken.com/v2"

# ----------- ENV / CONFIG -----------
SL_PCT = float(os.getenv("SL_PCT", "0.01"))
TP_PCT = float(os.getenv("TP_PCT", "0.02"))
PRICE_BUFFER_PCT = float(os.getenv("PRICE_BUFFER_PCT", "0.001"))

BE_ENABLE = os.getenv("BE_ENABLE", "1") in ("1","true","True","yes","on")
BE_TRIGGER_PCT = float(os.getenv("BE_TRIGGER_PCT", "0.01"))
BE_OFFSET_PCT  = float(os.getenv("BE_OFFSET_PCT", "0.0005"))

RECONCILE_CANCEL_SELLS = os.getenv("RECONCILE_CANCEL_SELLS", "1") in ("1","true","True","yes","on")

LOOP_SECS = int(os.getenv("PROTECT_LOOP_SECS", "15"))  # elke Xs check
QUOTE = os.getenv("QUOTE", "USD")

KRAKEN_KEY = os.getenv("KRAKEN_KEY")
KRAKEN_SECRET = os.getenv("KRAKEN_SECRET")
if not KRAKEN_KEY or not KRAKEN_SECRET:
    raise SystemExit("KRAKEN_KEY/SECRET ontbreken")

# ----------- WS TOKEN CACHE -----------
_WS_TOKEN: Optional[str] = None
_WS_TOKEN_EXP: float = 0.0  # epoch sec

def _ws_token_valid() -> bool:
    return _WS_TOKEN is not None and time.time() < _WS_TOKEN_EXP

async def _get_ws_token(session: aiohttp.ClientSession) -> str:
    global _WS_TOKEN, _WS_TOKEN_EXP
    if _ws_token_valid():
        return _WS_TOKEN  # cached
    res = await private_post(session, "/0/private/GetWebSocketsToken", {})
    tok = res.get("token")
    if not tok:
        raise RuntimeError("No WS token")
    # Token is 15 min geldig → 14 min cache + wat marge
    _WS_TOKEN = tok
    _WS_TOKEN_EXP = time.time() + 14*60
    return tok

async def _ws_order_once(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    # één WS-verbinding; gebruikt cached token
    async with aiohttp.ClientSession() as s:
        token = await _get_ws_token(s)
        payload = {"method": method, "params": {**params, "token": token}}
        async with s.ws_connect(WS_AUTH, heartbeat=15) as ws:
            await ws.send_json(payload)
            t0 = time.time()
            while time.time() - t0 < 10:
                msg = await ws.receive(timeout=2.0)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("method") == method or data.get("error") or data.get("success") is not None:
                        return data
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
    return {"error": "WS order timeout"}

async def ws_order(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Gebruik token-cache; refresh bij invalid token precies 1x."""
    global _WS_TOKEN, _WS_TOKEN_EXP
    rep = await _ws_order_once(method, params)
    # Detecteer token/authorize fouten en probeer 1x te verversen
    err = (rep or {}).get("error") or ""
    if isinstance(err, list): err = " ".join(err)
    if "token" in str(err).lower() or "authorize" in str(err).lower():
        _WS_TOKEN = None
        _WS_TOKEN_EXP = 0
        rep = await _ws_order_once(method, params)
    return rep

# ----------- HELPERS -----------
def ws2rest_pair(ws_pair: str) -> str:
    return ws_pair.replace("/", "")

def rest2ws_pair(rest_pair: str) -> str:
    return rest_pair[:-3] + "/" + rest_pair[-3:]

def round_down(x: float, dp: int) -> float:
    f = 10 ** dp
    return math.floor(x * f) / f

def round_near(x: float, dp: int) -> float:
    f = 10 ** dp
    return math.floor(x * f + 0.5) / f

async def private_post(session: aiohttp.ClientSession, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
    nonce = str(int(time.time() * 1000))
    body = {"nonce": nonce, **data}
    postdata = urllib.parse.urlencode(body)
    sha = hashlib.sha256((nonce + postdata).encode()).digest()
    mac = hmac.new(base64.b64decode(KRAKEN_SECRET), (path.encode() + sha), hashlib.sha512)
    sig = base64.b64encode(mac.digest()).decode()
    headers = {
        "API-Key": KRAKEN_KEY,
        "API-Sign": sig,
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "User-Agent": "momentum/protectd"
    }
    async with session.post(API + path, data=body, headers=headers, timeout=30) as r:
        r.raise_for_status()
        js = await r.json()
        if js.get("error"):
            raise RuntimeError(f"{path} error: {js['error']}")
        return js["result"]

async def public_get(session: aiohttp.ClientSession, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    async with session.get(API + path, params=params, timeout=30) as r:
        r.raise_for_status()
        js = await r.json()
        if js.get("error"):
            raise RuntimeError(f"{path} error: {js['error']}")
        return js["result"]

# ----------- EXCHANGE QUERIES -----------
async def balances_ex(session) -> Dict[str, Dict[str, str]]:
    return await private_post(session, "/0/private/BalanceEx", {})

async def open_orders(session) -> Dict[str, Any]:
    return await private_post(session, "/0/private/OpenOrders", {})

async def trades_history(session, ofs=0) -> Dict[str, Any]:
    return await private_post(session, "/0/private/TradesHistory", {"ofs": ofs})

async def asset_pairs(session, rest_pairs: List[str]) -> Dict[str, Any]:
    res = await public_get(session, "/0/public/AssetPairs", {"pair": ",".join(rest_pairs)})
    return res

async def ticker_last(session, rest_pair: str) -> float:
    res = await public_get(session, "/0/public/Ticker", {"pair": rest_pair})
    data = next(iter(res.values()))
    last = float(data["c"][0])
    return last

# ----------- VWAP ENTRY PRICE -----------
async def infer_entry_price(session, rest_pair: str, base_qty: float) -> Optional[float]:
    needed = base_qty
    chunks: List[Tuple[float,float]] = []
    ofs = 0
    while needed > 1e-12 and ofs < 5000:
        hist = await trades_history(session, ofs=ofs)
        trs = list(hist.get("trades", {}).values())
        if not trs: break
        trs.sort(key=lambda t: t["time"])
        for t in trs:
            if t.get("pair") != rest_pair: 
                continue
            if t.get("type") != "buy":
                continue
            vol = float(t["vol"])
            price = float(t["price"])
            if vol <= 0: 
                continue
            take = min(needed, vol)
            chunks.append((take, price))
            needed -= take
            if needed <= 1e-12:
                break
        if hist.get("count", 0) <= ofs + len(trs):
            break
        ofs += len(trs)
    if needed > 1e-8:
        return None
    num = sum(q*p for q,p in chunks)
    den = sum(q for q,_ in chunks)
    return num/den if den>0 else None

# ----------- UTIL: open orders helpers -----------
async def cancel_all_sells_for_pair(session, rest_pair: str) -> List[str]:
    oo = await open_orders(session)
    ids = []
    for txid, od in (oo.get("open") or {}).items():
        descr = od.get("descr", {})
        if descr.get("pair") == rest_pair and descr.get("type") == "sell":
            ids.append(txid)
    replies = []
    for oid in ids:
        rep = await ws_order("cancel_order", {"order_id": [oid]})
        replies.append(rep)
    return ids

async def find_sell_order_for_pair(session, rest_pair: str) -> Optional[Tuple[str, Dict[str,Any]]]:
    oo = await open_orders(session)
    for txid, od in (oo.get("open") or {}).items():
        descr = od.get("descr", {})
        if descr.get("pair") == rest_pair and descr.get("type") == "sell":
            return txid, od
    return None

# ----------- CORE: plaats SL / TP / EDIT / MARKET -----------
async def place_sl(ws_pair: str, qty: float, sl_trig: float, sl_limit: float) -> Dict[str,Any]:
    return await ws_order("add_order", {
        "order_type": "stop-loss-limit",
        "side": "sell",
        "order_qty": qty,
        "symbol": ws_pair,
        "time_in_force": "gtc",
        "triggers": {"reference": "last", "price": sl_trig, "price_type": "static"},
        "limit_price": sl_limit,
    })

async def place_tp(ws_pair: str, qty: float, tp_trig: float, tp_limit: float) -> Dict[str,Any]:
    return await ws_order("add_order", {
        "order_type": "take-profit-limit",
        "side": "sell",
        "order_qty": qty,
        "symbol": ws_pair,
        "time_in_force": "gtc",
        "triggers": {"reference": "last", "price": tp_trig, "price_type": "static"},
        "limit_price": tp_limit,
    })

async def edit_sl_raise(order_id: str, ws_pair: str, qty: float, new_trig: float, new_limit: float) -> Dict[str,Any]:
    # LET OP: geen 'order_type' bij edit_order sturen
    return await ws_order("edit_order", {
        "order_id": order_id,
        "symbol": ws_pair,
        "order_qty": qty,
        "time_in_force": "gtc",
        "triggers": {"reference": "last", "price": new_trig, "price_type": "static"},
        "limit_price": new_limit,
    })

async def market_sell(ws_pair: str, qty: float) -> Dict[str,Any]:
    return await ws_order("add_order", {
        "order_type": "market",
        "side": "sell",
        "order_qty": qty,
        "symbol": ws_pair,
        "time_in_force": "ioc",
    })

# ----------- MAIN LOOP -----------
async def run_once():
    out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "result": []}
    async with aiohttp.ClientSession() as s:
        bals = await balances_ex(s)  # {"ZUSD": {...}, "SNX": {"balance": "...", "hold_trade": "..."}}
        # holdings: alleen assets met free > 0 óf hold_trade > 0 (want positie bestaat, al is free 0)
        holdings = []
        for asset, data in bals.items():
            if asset in (f"Z{QUOTE}", QUOTE):
                continue
            free = float(str(data.get("available") or data.get("balance") or 0.0))
            hold_trade = float(str(data.get("hold_trade") or 0.0))
            if free > 0 or hold_trade > 0:
                rest_pair = f"{asset}{QUOTE}" if asset.isupper() else f"{asset.upper()}{QUOTE}"
                ws_pair = rest2ws_pair(rest_pair)
                qty_seen = free if free > 0 else hold_trade  # wat we proberen te beschermen/sluiten
                holdings.append((asset, rest_pair, ws_pair, free, hold_trade, qty_seen))

        if not holdings:
            print(json.dumps({"ts": out["ts"], "result": [], "note": "no holdings"}))
            return

        pairs = [h[1] for h in holdings]
        ap = await asset_pairs(s, pairs)

        for asset, rest_pair, ws_pair, qty_free, qty_hold, qty_seen in holdings:
            meta = ap.get(rest_pair) or {}
            price_dp = int(meta.get("pair_decimals", 5))
            lot_dp   = int(meta.get("lot_decimals", 8))
            ordermin = float(meta.get("ordermin", 0.0) or 0.0)
            last = await ticker_last(s, rest_pair)

            entry = await infer_entry_price(s, rest_pair, qty_free + qty_hold)  # neem hele netpos mee
            ref_price = entry or last  # fallback conservatief

            sl_trig = round_near(ref_price * (1.0 - SL_PCT), price_dp)
            sl_limit = round_near(sl_trig * (1.0 - PRICE_BUFFER_PCT), price_dp)

            tp_trig = round_near(ref_price * (1.0 + TP_PCT), price_dp)
            tp_limit = round_near(tp_trig * (1.0 - PRICE_BUFFER_PCT), price_dp)

            be_trig = round_near(ref_price * (1.0 + BE_TRIGGER_PCT), price_dp)
            be_stop = round_near(ref_price * (1.0 + BE_OFFSET_PCT), price_dp)
            be_limit = round_near(be_stop * (1.0 - PRICE_BUFFER_PCT), price_dp)

            qty = round_down(qty_seen, lot_dp)
            if ordermin and qty < ordermin:
                out["result"].append({"pair": ws_pair, "skip": "qty_below_ordermin", "qty": qty, "ordermin": ordermin})
                continue

            action = {"pair": ws_pair, "qty": qty, "price_dp": price_dp, "lot_dp": lot_dp, "ordermin": ordermin,
                      "last": last, "entry": entry, "sl_trig": sl_trig, "sl_limit": sl_limit,
                      "tp_trig": tp_trig, "tp_limit": tp_limit, "be_trig": be_trig, "be_stop": be_stop,
                      "free": qty_free, "hold_trade": qty_hold}

            existing = await find_sell_order_for_pair(s, rest_pair)
            if existing:
                oid, oinfo = existing
                otype = oinfo.get("descr", {}).get("ordertype", "")
                action["existing_sell"] = {"id": oid, "type": otype}

                # ---- TP SWITCH (alleen als dit de positie verbetert = in winst) ----
                if last >= tp_trig and "stop" in otype:
                    if RECONCILE_CANCEL_SELLS:
                        cancel_rep = await ws_order("cancel_order", {"order_id": [oid]})
                        action["tp_switch_cancel_sl"] = cancel_rep

                    # wacht tot base vrij is (free >= qty) of 4s
                    freed = False
                    t0 = time.time()
                    while time.time() - t0 < 4.0:
                        bals2 = await balances_ex(s)
                        free2 = float(str(bals2.get(asset, {}).get("available") or 0.0))
                        if free2 + 1e-9 >= qty:
                            freed = True
                            break
                        await asyncio.sleep(0.25)
                    action["tp_wait_freed"] = {"freed": freed}

                    # eerst TP proberen
                    tp_rep = await place_tp(ws_pair, qty, tp_trig, tp_limit)
                    action["tp_place"] = tp_rep

                    if not tp_rep.get("success"):
                        # TP niet gelukt → SL direct terugzetten (zelfde niveau als berekend)
                        sl_back = await place_sl(ws_pair, qty, sl_trig, sl_limit)
                        action["tp_place_fallback_sl"] = sl_back

                    out["result"].append(action)
                    continue

                # ---- BE omhoog (nooit naar beneden) ----
                if BE_ENABLE and "stop" in otype and last >= be_trig:
                    # alleen als be_stop >= huidige SL-trigger (geen daling)
                    new_trig = max(be_stop, sl_trig)
                    new_limit = max(be_limit, sl_limit)
                    ed = await edit_sl_raise(oid, ws_pair, qty, new_trig, new_limit)
                    action["be_amend"] = ed
                    out["result"].append(action)
                    continue

                # Anders: bestaande SELL laten staan
                out["result"].append(action)
                continue

            # ---- GEEN SELL OPEN ----
            # Fail-safe: prijs onder SL-trigger → market close
            if last <= sl_trig:
                ms = await market_sell(ws_pair, qty)
                action["market_sell"] = ms
                out["result"].append(action)
                continue

            # Als we in winst zijn, direct TP plaatsen (verbetert positie)
            if last >= tp_trig:
                tp_rep = await place_tp(ws_pair, qty, tp_trig, tp_limit)
                action["tp_place"] = tp_rep
                if not tp_rep.get("success"):
                    # TP plaatsen faalde → zet SL om niet naakt te staan
                    sl_rep = await place_sl(ws_pair, qty, sl_trig, sl_limit)
                    action["tp_place_fallback_sl"] = sl_rep
                out["result"].append(action)
                continue

            # Baseline: onder TP-trigger → SL plaatsen
            sl_rep = await place_sl(ws_pair, qty, sl_trig, sl_limit)
            action["sl_place"] = sl_rep
            out["result"].append(action)

    print(json.dumps(out, indent=2))

async def main_loop():
    while True:
        try:
            await run_once()
        except Exception as e:
            print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "error": str(e)}))
        await asyncio.sleep(LOOP_SECS)

if __name__ == "__main__":
    asyncio.run(main_loop())
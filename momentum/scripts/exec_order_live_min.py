#!/usr/bin/env python3
import os, json, hmac, time, base64, hashlib, asyncio, argparse
from datetime import datetime, timezone, timedelta
import aiohttp
import websockets

API_URL = "https://api.kraken.com"
WS_AUTH_URL = "wss://ws-auth.kraken.com/v2"

def load_env():
    key = os.environ.get("KRAKEN_KEY")
    sec = os.environ.get("KRAKEN_SECRET")
    if not key or not sec:
        raise SystemExit("Missing KRAKEN_KEY/SECRET in environment (.env)")
    return key, sec

def _sign_kraken(path, data, secret_b64):
    postdata = "&".join(f"{k}={v}" for k,v in data.items())
    nonce = data.get("nonce", "")
    sha256 = hashlib.sha256((nonce + postdata).encode()).digest()
    msg = path.encode() + sha256
    mac = hmac.new(base64.b64decode(secret_b64), msg, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()

async def get_ws_token(session, key, secret_b64):
    path = "/0/private/GetWebSocketsToken"
    url = API_URL + path
    nonce = str(int(time.time() * 1000))
    data = {"nonce": nonce}
    headers = {
        "API-Key": key,
        "API-Sign": _sign_kraken(path, data, secret_b64),
        "User-Agent": "momentum-exec-live-min/1.1"
    }
    async with session.post(url, data=data, headers=headers) as resp:
        js = await resp.json()
        if not js.get("result") or "token" not in js["result"]:
            raise RuntimeError(f"GetWebSocketsToken failed: {js}")
        return js["result"]["token"]

def build_add_order(symbol, side, qty, limit, tif, validate, token, req_id):
    # deadline: RFC3339 met milliseconden, binnen ~5s
    ts = datetime.now(timezone.utc) + timedelta(seconds=5)
    deadline = ts.isoformat(timespec='milliseconds').replace('+00:00','Z')
    return {
        "method": "add_order",
        "params": {
            "order_type": "limit",
            "side": side,
            "order_qty": float(qty),
            "symbol": symbol,
            "time_in_force": tif,
            "reduce_only": False,
            "margin": False,
            "stp_type": "cancel_newest",
            "deadline": deadline,
            "validate": bool(int(validate)),
            "limit_price": float(limit),
            "token": token
        },
        "req_id": req_id
    }

def looks_like_final(msg):
    if isinstance(msg, dict):
        if msg.get("method") == "add_order":
            return True
        if msg.get("success") is not None and msg.get("method") in (None, "add_order"):
            return True
        if msg.get("error") is not None and msg.get("method") in (None, "add_order"):
            return True
    return False

async def run(symbol, side, qty, limit_price, tif, validate):
    key, sec = load_env()
    entry_max = float(os.environ.get("ENTRY_MAX_NOTIONAL", "10"))
    if float(qty) * float(limit_price) > entry_max:
        raise SystemExit(f"ENTRY_MAX_NOTIONAL exceeded ({qty}*{limit_price} > {entry_max})")

    async with aiohttp.ClientSession() as session:
        token = await get_ws_token(session, key, sec)

    req_id = int(time.time() * 1000) % 10_000_000
    payload = build_add_order(symbol, side, qty, limit_price, tif, validate, token, req_id)

    outbox = {"sent": payload, "received": []}
    async with websockets.connect(WS_AUTH_URL, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps(payload))
        deadline = time.time() + 8.0
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"raw": raw}
            outbox["received"].append(msg)
            # sla status/heartbeat over
            if isinstance(msg, dict) and msg.get("channel") == "status":
                continue
            if looks_like_final(msg):
                break
            if time.time() >= deadline:
                break
    print(json.dumps(outbox, indent=2))

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--side", choices=["buy","sell"], required=True)
    ap.add_argument("--qty", type=float, required=True)
    ap.add_argument("--limit", type=float, required=True)
    ap.add_argument("--tif", default="gtc")
    ap.add_argument("--validate", default="1")
    args = ap.parse_args(argv)
    asyncio.run(run(args.symbol, args.side, args.qty, args.limit, args.tif, args.validate))

if __name__ == "__main__":
    main()

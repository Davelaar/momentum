import os, json, asyncio, aiohttp, sys, argparse, time

WS_AUTH_URL = "wss://ws-auth.kraken.com/v2"

async def get_ws_token(session):
    # Use the existing KrakenREST private post via simple inline (no external deps)
    # We re-implement the minimal signing here to avoid importing your whole client.
    import urllib.parse, hashlib, hmac, base64
    KRAKEN_API = "https://api.kraken.com"
    path = "/0/private/GetWebSocketsToken"
    key = os.getenv("KRAKEN_KEY")
    sec = os.getenv("KRAKEN_SECRET")
    if not key or not sec:
        raise RuntimeError("Missing KRAKEN_KEY/SECRET for WS auth token")
    nonce = str(int(time.time() * 1000))
    data = {"nonce": nonce}
    postdata = urllib.parse.urlencode(data)
    message = (nonce + postdata).encode()
    sha256 = hashlib.sha256(message).digest()
    mac = hmac.new(base64.b64decode(sec), (path.encode() + sha256), hashlib.sha512)
    sig = base64.b64encode(mac.digest()).decode()
    headers = {
        "API-Key": key,
        "API-Sign": sig,
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "User-Agent": "momentum/ws-equity-cache"
    }
    async with session.post(KRAKEN_API + path, data=data, headers=headers, timeout=30) as r:
        r.raise_for_status()
        payload = await r.json()
        if payload.get("error"):
            raise RuntimeError(f"Kraken error: {payload['error']}")
        tok = payload["result"]["token"]
        if not tok:
            raise RuntimeError("No token in GetWebSocketsToken result")
        return tok

async def fetch_usd_equity_via_ws():
    async with aiohttp.ClientSession() as session:
        token = await get_ws_token(session)
        async with session.ws_connect(WS_AUTH_URL, heartbeat=15) as ws:
            sub = {"method":"subscribe","params":{"channel":"balances","token": token}}
            await ws.send_json(sub)
            usd = None
            # Wait up to ~10 messages / 10s for a snapshot
            for _ in range(20):
                msg = await ws.receive(timeout=1.0)
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except Exception:
                        continue
                    # Ack? ignore
                    if data.get("success") is True and data.get("result",{}).get("channel") == "balances":
                        continue
                    if data.get("channel") == "balances" and data.get("type") == "snapshot":
                        # scan snapshot for USD
                        for it in data.get("data", []):
                            if it.get("asset") == "USD":
                                usd = float(it.get("balance") or 0.0)
                                break
                        break
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
            if usd is None:
                raise RuntimeError("No USD balance found in balances snapshot")
            return usd

def main():
    ap = argparse.ArgumentParser(description="Update local equity cache (USD) via Kraken WS v2 balances snapshot")
    ap.add_argument("--out", type=str, default=None, help="Output file (defaults to $APP/var/account_equity_usd.json)")
    args = ap.parse_args()
    app = os.environ.get("APP", ".")
    out = args.out or os.path.join(app, "var", "account_equity_usd.json")
    usd = asyncio.run(fetch_usd_equity_via_ws())
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"equity_usd": usd, "source":"ws_v2_balances"}, f)
    print(json.dumps({"out": out, "equity_usd": usd, "source":"ws_v2_balances"}))

if __name__ == "__main__":
    main()
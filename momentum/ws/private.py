
import os
import json
import base64
import hashlib
import hmac
import time
import asyncio
from typing import Dict, Any, Optional

import aiohttp
import websockets
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # optional

WS_V2_URL = os.environ.get("KRAKEN_WS_V2_URL", "wss://ws.kraken.com/v2")
WS_V1_AUTH_URL = os.environ.get("KRAKEN_WS_V1_AUTH_URL", "wss://ws-auth.kraken.com/")
REST_BASE = os.environ.get("KRAKEN_REST_BASE", "https://api.kraken.com")

def _now_ms() -> int:
    return int(time.time() * 1000)

# ---------- REST auth helpers -------------------------------------------------------
def _sign(path: str, data: Dict[str, str], secret_b64: str) -> str:
    nonce = data.get("nonce") or str(_now_ms())
    postdata = "&".join([f"{k}={v}" for k, v in data.items()])
    sha = hashlib.sha256((nonce + postdata).encode()).digest()
    mac = hmac.new(base64.b64decode(secret_b64), (path.encode() + sha), hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()

async def _rest_private(session: aiohttp.ClientSession, path: str, payload: Dict[str, str]) -> Dict[str, Any]:
    key = os.environ.get("KRAKEN_KEY")
    secret_b64 = os.environ.get("KRAKEN_SECRET")
    if not key or not secret_b64:
        raise RuntimeError("Missing KRAKEN_KEY/SECRET for REST call")
    payload = dict(payload)
    payload["nonce"] = payload.get("nonce") or str(_now_ms())
    url = REST_BASE + path
    headers = {
        "API-Key": key,
        "API-Sign": _sign(path, payload, secret_b64),
    }
    async with session.post(url, data=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        resp.raise_for_status()
        j = await resp.json()
        if j.get("error"):
            raise RuntimeError(f"Kraken REST error on {path}: {j['error']}")
        return j["result"]

# ------------- Token fetch via REST (fallback if KRAKEN_WS_TOKEN not set) ----------
async def get_ws_token(session: aiohttp.ClientSession) -> str:
    # reuse REST helper
    res = await _rest_private(session, "/0/private/GetWebSocketsToken", {})
    return res["token"]

# ------------- State store with debounced flush ------------------------------------
class DebouncedState:
    def __init__(self, path: str, flush_interval: float = 1.0):
        self.path = path
        self.flush_interval = flush_interval
        self._lock = asyncio.Lock()
        self._dirty = False
        self._data: Dict[str, Any] = {}

    async def load(self):
        try:
            with open(self.path, "r") as f:
                self._data = json.load(f)
        except FileNotFoundError:
            self._data = {}

    async def upsert(self, key: str, update: Dict[str, Any]):
        async with self._lock:
            cur = self._data.get(key, {})
            cur.update(update)
            self._data[key] = cur
            self._dirty = True

    async def loop_flush(self):
        while True:
            await asyncio.sleep(self.flush_interval)
            if self._dirty:
                async with self._lock:
                    tmp = self.path + ".tmp"
                    with open(tmp, "w") as f:
                        json.dump(self._data, f, separators=(",", ":"), sort_keys=True)
                    os.replace(tmp, self.path)
                    self._dirty = False

# ------------- Private WS manager --------------------------------------------------
class PrivateWSManager:
    def __init__(self, app_path: Optional[str] = None):
        self.app_path = app_path or os.environ.get("APP", ".")
        if load_dotenv:
            env_path = os.path.join(self.app_path, ".env")
            if os.path.exists(env_path):
                load_dotenv(env_path)
        var = os.path.join(self.app_path, "var")
        os.makedirs(var, exist_ok=True)
        self.hb_path = os.path.join(var, "private_ws_hb.txt")
        self.err_path = os.path.join(var, "private_ws_last_err.txt")
        self.oo_state = DebouncedState(os.path.join(var, "open_orders_state.json"))
        self.ot_state = DebouncedState(os.path.join(var, "own_trades_state.json"))

    async def run(self):
        await self.oo_state.load()
        await self.ot_state.load()
        flusher = asyncio.gather(self.oo_state.loop_flush(), self.ot_state.loop_flush())
        try:
            # Seed from REST once, then switch to WS stream
            async with aiohttp.ClientSession(headers={"User-Agent": "momentum-ws-private/0.1"}) as session:
                await self._seed_from_rest(session)
            ok = await self._loop_v2()
            if not ok:
                await self._loop_v1()
        finally:
            flusher.cancel()

    # --------- Initial REST snapshot to seed files ---------------------------------
    async def _seed_from_rest(self, session: aiohttp.ClientSession):
        try:
            # OpenOrders (no_trades true keeps payload small)
            oo = await _rest_private(session, "/0/private/OpenOrders", {"trades": "false"})
            open_map = oo.get("open", {})
            for oid, data in open_map.items():
                await self.oo_state.upsert(oid, data)
            # TradesHistory (recent subset)
            th = await _rest_private(session, "/0/private/TradesHistory", {"ofs": "0"})
            trades = th.get("trades", {})
            for tid, data in trades.items():
                await self.ot_state.upsert(tid, data)
            # Force immediate flush after seed
            await asyncio.sleep(0.1)
        except Exception as e:
            # Non-fatal: continue to WS anyway; error recorded
            try:
                with open(self.err_path, "a") as f:
                    f.write(f"\n{int(time.time())} seed REST error: {type(e).__name__}: {e}")
            except Exception:
                pass

    # ---------------------- WS v2/v1 loops -----------------------------------------
    async def _loop_v2(self) -> bool:
        attempt = 0
        while True:
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": "momentum-ws-private/0.1"}) as session:
                    token = os.environ.get("KRAKEN_WS_TOKEN") or await get_ws_token(session)
                async with websockets.connect(WS_V2_URL, ping_interval=30, ping_timeout=10, close_timeout=10, max_queue=1024) as ws:
                    # authorize + subscribe
                    await ws.send(json.dumps({"method": "authorize", "params": {"token": token}}))
                    for ch in ("openOrders", "ownTrades"):
                        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": ch}}))
                    # tasks
                    async def heartbeat():
                        while True:
                            with open(self.hb_path, "w") as f:
                                f.write(str(int(time.time())))
                            await asyncio.sleep(5)
                    async def receiver():
                        while True:
                            raw = await ws.recv()
                            msg = json.loads(raw)
                            await self._handle_v2(msg)
                    tasks = [asyncio.create_task(heartbeat()), asyncio.create_task(receiver())]
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                    for t in pending:
                        t.cancel()
                return True
            except Exception as e:
                attempt += 1
                try:
                    with open(self.err_path, "a") as f:
                        f.write(f"\n{int(time.time())} v2 {type(e).__name__}: {e}")
                except Exception:
                    pass
                await asyncio.sleep(min(300, 2 ** attempt))
                if attempt > 10:
                    return False

    async def _loop_v1(self) -> bool:
        attempt = 0
        while True:
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": "momentum-ws-private/0.1"}) as session:
                    token = os.environ.get("KRAKEN_WS_TOKEN") or await get_ws_token(session)
                async with websockets.connect(WS_V1_AUTH_URL, ping_interval=30, ping_timeout=10, close_timeout=10, max_queue=1024) as ws:
                    for name in ("openOrders", "ownTrades"):
                        await ws.send(json.dumps({"event": "subscribe", "subscription": {"name": name, "token": token}}))
                    async def heartbeat():
                        while True:
                            with open(self.hb_path, "w") as f:
                                f.write(str(int(time.time())))
                            await asyncio.sleep(5)
                    async def receiver():
                        while True:
                            raw = await ws.recv()
                            msg = json.loads(raw)
                            await self._handle_v1(msg)
                    tasks = [asyncio.create_task(heartbeat()), asyncio.create_task(receiver())]
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                    for t in pending:
                        t.cancel()
                return True
            except Exception as e:
                attempt += 1
                try:
                    with open(self.err_path, "a") as f:
                        f.write(f"\n{int(time.time())} v1 {type(e).__name__}: {e}")
                except Exception:
                    pass
                await asyncio.sleep(min(300, 2 ** attempt))

    # ---------------- Message handlers ------------------------------------
    async def _handle_v2(self, msg: Dict[str, Any]):
        ch = msg.get("channel")
        if ch == "openOrders":
            await self._handle_open_orders_v2(msg)
        elif ch == "ownTrades":
            await self._handle_own_trades_v2(msg)

    async def _handle_v1(self, msg: Dict[str, Any]):
        if isinstance(msg, dict) and msg.get("event") in ("heartbeat", "systemStatus", "subscriptionStatus"):
            return
        if isinstance(msg, list) and len(msg) >= 3:
            payload, channel = msg[1], msg[2]
            if channel == "openOrders":
                await self._handle_open_orders_v1(payload)
            elif channel == "ownTrades":
                await self._handle_own_trades_v1(payload)

    async def _handle_open_orders_v2(self, msg: Dict[str, Any]):
        items = msg.get("data", [])
        for it in items:
            oid = it.get("orderid") or it.get("txid") or it.get("orderTxid")
            if not oid:
                continue
            await self.oo_state.upsert(oid, it)

    async def _handle_open_orders_v1(self, payload: Dict[str, Any]):
        for section in ("open", "change"):
            sec = payload.get(section, {})
            for oid, data in sec.items():
                await self.oo_state.upsert(oid, data)
        for oid, data in payload.get("close", {}).items():
            await self.oo_state.upsert(oid, data)

    async def _handle_own_trades_v2(self, msg: Dict[str, Any]):
        items = msg.get("data", [])
        for it in items:
            tid = it.get("tradeid") or it.get("txid")
            if not tid:
                continue
            await self.ot_state.upsert(tid, it)

    async def _handle_own_trades_v1(self, payload: Dict[str, Any]):
        trades = payload.get("trades", payload)
        if isinstance(trades, dict):
            for tid, data in trades.items():
                await self.ot_state.upsert(tid, data)
        elif isinstance(trades, list):
            for it in trades:
                tid = it.get("tradeid") or it.get("txid")
                if tid:
                    await self.ot_state.upsert(tid, it)


from __future__ import annotations
import asyncio, json, os, time
import aiohttp
from ..util.backoff import exp_backoff, CircuitBreaker

WS_AUTH_URL = "wss://ws-auth.kraken.com/v2"
USER_AGENT = "momentum/step10-fix5"

def _json(msg: dict) -> str:
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False)

async def _get_ws_token(session: aiohttp.ClientSession) -> str:
    from ..kraken.rest_client import KrakenREST
    kr = KrakenREST(session=session)
    res = await kr._post_private("GetWebSocketsToken", {})
    return res["token"]

def _map_tif(tif: str) -> str:
    tif = (tif or "gtc").lower()
    return {"gtc":"gtc","gtd":"gtd","ioc":"ioc"}.get(tif, "gtc")

class AddOrderExecutor:
    def __init__(self, session: aiohttp.ClientSession | None = None, max_retries: int = 5, breaker: CircuitBreaker | None = None):
        self._own_session = session is None
        self.session = session or aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})
        self.max_retries = max_retries
        self.breaker = breaker or CircuitBreaker()

    async def close(self):
        if self._own_session:
            await self.session.close()

    async def add_order(self, *, pair: str, side: str, ordertype: str, volume: float, price: float | None = None, price2: float | None = None, tif: str = "gtc", post_only: int = 0, validate: int = 1, client_id: str | None = None, userref: int | None = None, extras: dict | None = None) -> dict:
        if not self.breaker.allow():
            return {"status":"blocked","reason":"circuit_open"}

        token = os.getenv("KRAKEN_WS_TOKEN") or await _get_ws_token(self.session)
        params = {
            "order_type": ordertype,
            "side": side,
            "order_qty": float(volume),
            "symbol": pair,  # USE AS GIVEN (e.g. BTC/USD)
            "time_in_force": _map_tif(tif),
            "post_only": bool(post_only),
            "validate": bool(validate),
            "token": token,
        }
        if client_id: params["cl_ord_id"] = client_id
        if userref is not None: params["order_userref"] = int(userref)
        if price is not None: params["limit_price"] = float(price)
        if extras: params.update(extras)

        req_id = int(time.time() * 1000)
        payload = {"method":"add_order","params":params,"req_id":req_id}

        attempt = 0
        last_err = None
        while attempt < self.max_retries:
            attempt += 1
            try:
                ws = await self.session.ws_connect(WS_AUTH_URL, heartbeat=25)
                await ws.send_str(_json(payload))

                deadline = asyncio.get_event_loop().time() + 12.0
                while True:
                    timeout = max(0.1, deadline - asyncio.get_event_loop().time())
                    if timeout <= 0:
                        raise asyncio.TimeoutError("timeout waiting for add_order ack")
                    msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    data = json.loads(msg.data)
                    # Look for a frame referencing our method/req_id or containing success/result
                    if data.get("method") == "add_order" or data.get("req_id") == req_id or "result" in data or "success" in data:
                        await ws.close()
                        if data.get("success") is True and "result" in data:
                            self.breaker.record_success()
                            return {"status":"ok","ack":data}
                        else:
                            self.breaker.record_failure()
                            last_err = data
                            err_s = json.dumps(data).lower()
                            if "rate" in err_s or "429" in err_s:
                                await asyncio.sleep(exp_backoff(attempt))
                                break
                            return {"status":"error","ack":data}
                await ws.close()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.breaker.record_failure()
                last_err = {"error":str(e)}
                await asyncio.sleep(exp_backoff(attempt))
        return {"status":"error","reason":"max_retries","last": last_err}

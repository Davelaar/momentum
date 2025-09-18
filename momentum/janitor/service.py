from __future__ import annotations
import os, time, json, asyncio
import aiohttp
from ..state.json_safety import read_json_dict, read_json_list, write_json
from ..util.rate_limit import TokenBucket

WS_AUTH_URL = "wss://ws-auth.kraken.com/v2"

def _log(app: str, level: str, msg: str, **kv):
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "lvl": level, "msg": msg, **kv}
    try:
        print(json.dumps(line, ensure_ascii=False), flush=True)
    except Exception:
        pass
    try:
        path = os.path.join(app, "var", "janitor.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass

async def _get_token(session: aiohttp.ClientSession) -> str:
    from ..kraken.rest_client import KrakenREST
    kr = KrakenREST(session=session)
    res = await kr._post_private("GetWebSocketsToken", {})
    return res["token"]

async def _ws_call(method: str, params: dict, session: aiohttp.ClientSession) -> dict:
    req = {"method": method, "params": params, "req_id": int(time.time()*1000)}
    ws = await session.ws_connect(WS_AUTH_URL, heartbeat=25)
    try:
        await ws.send_str(json.dumps(req, separators=(",", ":"), ensure_ascii=False))
        deadline = asyncio.get_event_loop().time() + 10.0
        while asyncio.get_event_loop().time() < deadline:
            msg = await ws.receive(timeout=max(0.1, deadline - asyncio.get_event_loop().time()))
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            data = json.loads(msg.data)
            if data.get("method") == method or "success" in data or "result" in data:
                return data
        return {"success": False, "error": "timeout waiting for ack"}
    finally:
        await ws.close()

class Janitor:
    def __init__(self, app: str, rate_per_sec: float = 2.0, burst: int = 4, debounce_sec: int = 5):
        self.app = app
        self.bucket = TokenBucket(rate_per_sec, burst)
        self.debounce_sec = debounce_sec
        self.history_path = os.path.join(app, "var", "janitor_history.json")
        self.hist = read_json_dict(self.history_path) or {"done": {}, "last_seen": {}}

    def _seen_recent(self, key: str) -> bool:
        t = self.hist["last_seen"].get(key, 0)
        return (time.time() - t) < self.debounce_sec

    def _mark_seen(self, key: str):
        self.hist["last_seen"][key] = time.time()
        write_json(self.history_path, self.hist)

    def _mark_done(self, key: str, ack: dict):
        self.hist["done"][key] = {"ts": time.time(), "ack": ack}
        write_json(self.history_path, self.hist)

    async def run_once(self) -> None:
        _log(self.app, "info", "janitor_run_once_start")
        var = os.path.join(self.app, "var")
        actions = read_json_dict(os.path.join(var, "janitor_actions.json"))
        if not actions:
            _log(self.app, "info", "no actions")
            return

        cancel = actions.get("cancel") or []
        close  = actions.get("close") or []
        amend  = actions.get("amend") or []

        async with aiohttp.ClientSession() as sess:
            token = await _get_token(sess)

            for item in cancel:
                key = f"cancel:{item.get('cl_ord_id') or item.get('order_id')}"
                if not key or self._seen_recent(key):
                    continue
                if not self.bucket.allow():
                    _log(self.app, "warn", "rate_limited", action="cancel", key=key); continue
                params = {"token": token}
                if item.get("order_id"):
                    params["order_id"] = item["order_id"]
                elif item.get("cl_ord_id"):
                    params["cl_ord_id"] = item["cl_ord_id"]
                else:
                    _log(self.app, "error", "cancel_missing_id", item=item); continue
                ack = await _ws_call("cancel_order", params, sess)
                _log(self.app, "info", "cancel_ack", key=key, ack=ack)
                self._mark_done(key, ack); self._mark_seen(key)

            for item in close:
                pair = item.get("pair"); qty = item.get("qty"); side = item.get("side")
                key = f"close:{pair}:{side}:{qty}"
                if not pair or not qty or not side: 
                    _log(self.app, "error", "close_missing_fields", item=item); 
                    continue
                if self._seen_recent(key): 
                    continue
                if not self.bucket.allow():
                    _log(self.app, "warn", "rate_limited", action="close", key=key); continue
                params = {
                    "token": token,
                    "symbol": pair,
                    "side": side,
                    "order_type": "market",
                    "order_qty": float(qty),
                    "reduce_only": True,
                    "validate": False,
                }
                ack = await _ws_call("add_order", params, sess)
                _log(self.app, "info", "close_ack", key=key, ack=ack)
                self._mark_done(key, ack); self._mark_seen(key)

            for item in amend:
                key = f"amend:{item.get('cl_ord_id') or item.get('order_id')}"
                if self._seen_recent(key): 
                    continue
                if not self.bucket.allow():
                    _log(self.app, "warn", "rate_limited", action="amend", key=key); continue
                params = {"token": token}
                for fld in ("cl_ord_id","order_id","price","limit_price","order_qty","trigger_price","trigger_price_type"):
                    if fld in item:
                        params[fld] = item[fld]
                ack = await _ws_call("amend_order", params, sess)
                _log(self.app, "info", "amend_ack", key=key, ack=ack)
                self._mark_done(key, ack); self._mark_seen(key)

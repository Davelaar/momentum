
import os
import json
import asyncio
import random
import time
from typing import List, Dict, Any, Optional

import websockets

DEFAULT_WS_V2 = os.environ.get("KRAKEN_WS_V2_URL", "wss://ws.kraken.com/v2")
DEFAULT_WS_V1 = os.environ.get("KRAKEN_WS_V1_URL", "wss://ws.kraken.com/")

def _exp_backoff_with_jitter(attempt: int, base: float = 1.0, cap: float = 300.0) -> float:
    return random.uniform(0.0, min(cap, base * (2 ** attempt)))

def load_universe_pairs(app_path: Optional[str], limit: int) -> List[str]:
    app_path = app_path or os.environ.get("APP", ".")
    path = os.path.join(app_path, "var", "universe.json")
    with open(path, "r") as f:
        data = json.load(f)
    pairs = [u["pair"] for u in data.get("universe", [])]
    if limit and limit > 0:
        pairs = pairs[:limit]
    return pairs

class PublicWSManager:
    def __init__(self, app_path: Optional[str] = None):
        self.app_path = app_path or os.environ.get("APP", ".")
        self.ws_symbol_limit = int(os.environ.get("WS_SYMBOL_LIMIT", "24"))
        self.batch_size = int(os.environ.get("WS_BATCH_SIZE", "6"))
        self.batch_interval_ms = int(os.environ.get("WS_BATCH_INTERVAL_MS", "1200"))
        self.v2_url = os.environ.get("KRAKEN_WS_V2_URL", DEFAULT_WS_V2)
        self.v1_url = os.environ.get("KRAKEN_WS_V1_URL", DEFAULT_WS_V1)
        self.channel = os.environ.get("WS_PUBLIC_CHANNEL", "ticker")

    async def run(self) -> None:
        pairs = load_universe_pairs(self.app_path, self.ws_symbol_limit)
        ok = await self._connect_and_stream(self.v2_url, pairs, version=2)
        if not ok:
            await self._connect_and_stream(self.v1_url, pairs, version=1)

    async def _connect_and_stream(self, url: str, pairs: List[str], version: int) -> bool:
        attempt = 0
        while True:
            try:
                async with websockets.connect(url, ping_interval=30, ping_timeout=10, close_timeout=10, max_queue=1024) as ws:
                    await self._subscribe_in_batches(ws, pairs, version)
                    # Spawn tasks: receiver + periodic heartbeat writer
                    hb_path = os.path.join(self.app_path, "var", f"public_ws_v{version}_hb.txt")
                    log_path = os.path.join(self.app_path, "var", f"public_ws_v{version}.jsonl")
                    msg_counter = {"n": 0, "last_ts": 0}

                    async def heartbeat_writer():
                        while True:
                            ts = int(time.time())
                            try:
                                with open(hb_path, "w") as f:
                                    f.write(str(ts))
                            except Exception:
                                pass
                            await asyncio.sleep(5)  # write every 5s regardless of traffic

                    async def receiver():
                        while True:
                            msg = await ws.recv()
                            msg_counter["n"] += 1
                            msg_counter["last_ts"] = int(time.time())
                            # append compact JSON to log (bounded size rotation could be added later)
                            try:
                                with open(log_path, "a") as f:
                                    f.write(json.dumps({"ts": msg_counter["last_ts"], "data": json.loads(msg)}) + "\n")
                            except Exception:
                                pass

                    tasks = [asyncio.create_task(heartbeat_writer()), asyncio.create_task(receiver())]
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                    for t in pending:
                        t.cancel()
                return True
            except Exception as e:
                attempt += 1
                # log error quickly
                try:
                    errp = os.path.join(self.app_path, "var", f"public_ws_v{version}_last_err.txt")
                    with open(errp, "w") as f:
                        f.write(f"{int(time.time())} {type(e).__name__}: {e}")
                except Exception:
                    pass
                sleep_s = _exp_backoff_with_jitter(attempt)
                await asyncio.sleep(sleep_s)
                if attempt > 10 and version == 2:
                    return False

    async def _subscribe_in_batches(self, ws, pairs: List[str], version: int) -> None:
        for i in range(0, len(pairs), self.batch_size):
            chunk = pairs[i:i+self.batch_size]
            if version == 2:
                payload = {
                    "method": "subscribe",
                    "params": {
                        "channel": self.channel,
                        "symbol": chunk,
                    }
                }
            else:
                payload = {
                    "event": "subscribe",
                    "pair": chunk,
                    "subscription": {"name": self.channel},
                }
            await ws.send(json.dumps(payload))
            await asyncio.sleep(self.batch_interval_ms / 1000.0)

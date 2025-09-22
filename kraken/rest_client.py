
from __future__ import annotations
import aiohttp, asyncio, time, urllib.parse, hashlib, hmac, base64, os
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass

KRAKEN_API = "https://api.kraken.com"
USER_AGENT = "momentum/step10-fix5"

def _sign(path: str, data: dict, secret_b64: str) -> str:
    postdata = urllib.parse.urlencode(data)
    message = (data["nonce"] + postdata).encode()
    sha256 = hashlib.sha256(message).digest()
    mac = hmac.new(base64.b64decode(secret_b64), (path.encode() + sha256), hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()

class KrakenREST:
    def __init__(self, key: str | None = None, secret: str | None = None, session: aiohttp.ClientSession | None = None):
        self.key = key or os.getenv("KRAKEN_KEY")
        self.secret = secret or os.getenv("KRAKEN_SECRET")
        self._own = session is None
        self.session = session or aiohttp.ClientSession(headers={"User-Agent": USER_AGENT})

    async def close(self):
        if self._own:
            await self.session.close()

    async def _post_private(self, endpoint: str, data: dict | None = None) -> dict:
        if not self.key or not self.secret:
            raise RuntimeError("Missing KRAKEN_KEY/SECRET for private REST")
        data = dict(data or {})
        data["nonce"] = str(int(time.time() * 1000))
        path = f"/0/private/{endpoint}"
        sig = _sign(path, data, self.secret)
        headers = {"API-Key": self.key, "API-Sign": sig, "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}
        async with self.session.post(KRAKEN_API + path, data=data, headers=headers, timeout=30) as r:
            r.raise_for_status()
            payload = await r.json()
            if payload.get("error"):
                raise RuntimeError(f"Kraken error: {payload['error']}")
            return payload["result"]

    async def _post_public(self, endpoint: str, data: dict | None = None) -> dict:
        path = f"/0/public/{endpoint}"
        async with self.session.post(KRAKEN_API + path, data=data or {}, timeout=30) as r:
            r.raise_for_status()
            payload = await r.json()
            if payload.get("error"):
                raise RuntimeError(f"Kraken error: {payload['error']}")
            return payload["result"]

    async def asset_pairs(self) -> dict:
        return await self._post_public("AssetPairs", {})

    async def ticker_alt(self, altnames_csv: str) -> dict:
        return await self._post_public("Ticker", {"pair": altnames_csv})

    async def altname_for_wsname(self, wsname: str) -> str | None:
        ap = await self.asset_pairs()
        for v in ap.values():
            if v.get("wsname") == wsname:
                return v.get("altname")
        return None

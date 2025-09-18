
import os
import json
import asyncio
import time
from typing import Any, Dict, List, Optional
import aiohttp

KRAKEN_ASSETPAIRS_URL = os.environ.get("KRAKEN_ASSETPAIRS_URL", "https://api.kraken.com/0/public/AssetPairs")

def _now_ms() -> int:
    return int(time.time() * 1000)

async def fetch_assetpairs(session: aiohttp.ClientSession) -> Dict[str, Any]:
    async with session.get(KRAKEN_ASSETPAIRS_URL, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        resp.raise_for_status()
        return await resp.json()

async def get_pairs_filtered_usd(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    data = await fetch_assetpairs(session)
    if data.get("error"):
        raise RuntimeError(f"Kraken error: {data['error']}")
    result = data.get("result", {})

    out: List[Dict[str, Any]] = []
    for key, info in result.items():
        wsname = info.get("wsname") or info.get("altname")
        if not wsname:
            continue
        # Keep only pairs with '/USD' suffix in wsname (WS-compatible)
        if not wsname.endswith("/USD"):
            continue
        out.append({
            "pair": wsname,
            "tickrate_hz": None,
            "depth_quote_band": None,
            "spread_pct": None,
        })
    # Sort for stability
    out.sort(key=lambda x: x["pair"])
    return out

async def build_universe(app_path: Optional[str] = None) -> Dict[str, Any]:
    app_path = app_path or os.environ.get("APP", ".")
    var_dir = os.path.join(app_path, "var")
    os.makedirs(var_dir, exist_ok=True)

    async with aiohttp.ClientSession(headers={"User-Agent": "momentum-universe/0.1"}) as session:
        pairs = await get_pairs_filtered_usd(session)

    payload = {
        "generated_at": _now_ms(),
        "source": "Kraken REST AssetPairs",
        "filters": {"suffix": "/USD"},
        "count": len(pairs),
        "universe": pairs,
    }
    out_path = os.path.join(var_dir, "universe.json")
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    return {"path": out_path, "count": len(pairs)}


import asyncio
from typing import Dict, List, Tuple
from momentum.kraken.rest_client import KrakenREST

def _ticks_from_assetpairs(wsnames: List[str], ap: dict) -> Dict[str, Tuple[float, float]]:
    # returns wsname -> (price_tick, vol_step)
    out: Dict[str, Tuple[float, float]] = {}
    # Build map alt->ws from AssetPairs
    alt_to_ws = {}
    for alt, v in ap.items():
        ws = v.get("wsname")
        if ws:
            alt_to_ws[alt] = ws
    for alt, v in ap.items():
        ws = alt_to_ws.get(alt)
        if not ws or ws not in wsnames:
            continue
        pair_dec = v.get("pair_decimals", 8)  # price precision
        lot_dec  = v.get("lot_decimals", 8)   # volume precision
        price_tick = 10.0 ** (-int(pair_dec))
        vol_step   = 10.0 ** (-int(lot_dec))
        out[ws] = (price_tick, vol_step)
    return out

async def _specs(wsnames: List[str]) -> Dict[str, Tuple[float, float]]:
    kr = KrakenREST()
    try:
        ap = await kr.asset_pairs()
        return _ticks_from_assetpairs(wsnames, ap)
    finally:
        await kr.close()

def specs_sync(wsnames: List[str]) -> Dict[str, Tuple[float, float]]:
    return asyncio.get_event_loop().run_until_complete(_specs(wsnames))


import asyncio
from typing import Dict, List
from momentum.kraken.rest_client import KrakenREST

async def _mids_for_wsnames(wsnames: List[str]) -> Dict[str, float]:
    kr = KrakenREST()
    try:
        alt_for_ws = {}
        for ws in wsnames:
            alt = await kr.altname_for_wsname(ws)
            if alt:
                alt_for_ws[ws] = alt
        if not alt_for_ws:
            return {}
        alts = ",".join(alt_for_ws.values())
        tick = await kr.ticker_alt(alts)
        mids: Dict[str, float] = {}
        alt_to_ws = {alt: ws for ws, alt in alt_for_ws.items()}
        for alt, info in tick.items():
            try:
                ask = float(info.get("a", [0])[0])
                bid = float(info.get("b", [0])[0])
                mid = (ask + bid) / 2 if ask and bid else 0.0
            except Exception:
                mid = 0.0
            ws = alt_to_ws.get(alt)
            if ws:
                mids[ws] = mid
        return mids
    finally:
        await kr.close()

def mids_sync(wsnames: List[str]) -> Dict[str, float]:
    return asyncio.get_event_loop().run_until_complete(_mids_for_wsnames(wsnames))

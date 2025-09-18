
from __future__ import annotations
import argparse, asyncio, json, math

from ..kraken.rest_client import KrakenREST
from ..orders.executor import AddOrderExecutor

ALIASES = {"BTC":"XBT","DOGE":"XDG"}

def normalize_wsname(wsname: str) -> str:
    if "/" not in wsname: 
        return wsname
    b,q = [s.strip().upper() for s in wsname.split("/",1)]
    b = ALIASES.get(b,b)
    return f"{b}/{q}"

def ceil_to_step(x: float, step: float) -> float:
    return math.ceil(x / step) * step

async def size_for_pair(user_symbol: str, kr: KrakenREST):
    wsname = normalize_wsname(user_symbol)  # for metadata only
    alt = await kr.altname_for_wsname(wsname)
    if not alt:
        raise RuntimeError(f"AssetPairs lookup failed for {wsname}")
    tick = await kr.ticker_alt(alt)
    info = tick.get(alt, {})
    try:
        ask = float(info.get("a", [0])[0]); bid = float(info.get("b", [0])[0])
        mid = (ask + bid)/2 if (ask and bid) else 0.0
    except Exception:
        mid = 0.0

    # fetch lot_decimals/ordermin/costmin
    ap = await kr.asset_pairs()
    entry = next(v for v in ap.values() if v.get("altname")==alt)
    lot_dec = int(entry.get("lot_decimals",8))
    ordermin = float(entry.get("ordermin","0"))
    costmin = float(entry.get("costmin","0") or 0.0)

    # choose test price (50% of mid to avoid crossing); if mid==0 use heuristic defaults
    heur = {"BTC/USD": 25000.0, "ETH/USD": 1500.0}
    price = mid*0.5 if mid>0 else heur.get(user_symbol.upper(), 100.0)
    step = 10**(-lot_dec)
    vol = max(ordermin, (max(costmin, 12.0))/price)  # ensure >= 12 USD notional or costmin
    vol = ceil_to_step(vol, step)
    return {"wsname_meta": wsname, "altname": alt, "mid": mid, "ordermin": ordermin, "costmin": costmin, "lot_decimals": lot_dec, "step": step, "volume": vol, "price": price}

async def run_case(symbol: str):
    kr = KrakenREST()
    calc = await size_for_pair(symbol, kr)
    ex = AddOrderExecutor(max_retries=2)
    try:
        res = await ex.add_order(pair=symbol, side="buy", ordertype="limit", volume=calc["volume"], price=calc["price"], validate=1, tif="gtc", post_only=1)
        return {"symbol": symbol, "calc": calc, "res": res}
    finally:
        await ex.close()
        await kr.close()

def main():
    p = argparse.ArgumentParser(description="Smoketest WS v2 add_order (validate=1) with compliant sizing")
    p.add_argument("--pairs", default="BTC/USD,ETH/USD")
    args = p.parse_args()
    pairs = [s.strip() for s in args.pairs.split(",") if s.strip()]

    async def runner():
        out = {}
        for sym in pairs:
            try:
                r = await run_case(sym)
                ok = r["res"].get("status")=="ok"
                out[sym] = {
                    "ok": ok,
                    "price": r["calc"]["price"],
                    "volume": r["calc"]["volume"],
                    "costmin": r["calc"]["costmin"],
                    "wsname_meta": r["calc"]["wsname_meta"],
                    "altname": r["calc"]["altname"],
                    "snippet": json.dumps(r["res"])[:240],
                }
            except Exception as e:
                out[sym] = {"ok": False, "error": str(e)}
        print(json.dumps({"summary": out}, indent=2, ensure_ascii=False))
    asyncio.run(runner())

if __name__ == "__main__":
    main()

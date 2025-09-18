
from __future__ import annotations
import argparse, asyncio, json, sys
from ..orders.executor import AddOrderExecutor

async def run_case(pair: str, side: str, ordertype: str, volume: float, price: float | None, validate: int) -> dict:
    ex = AddOrderExecutor(max_retries=2)
    try:
        res = await ex.add_order(pair=pair, side=side, ordertype=ordertype, volume=volume, price=price, validate=validate, tif="gtc", post_only=1)
        return res
    finally:
        await ex.close()

def main():
    p = argparse.ArgumentParser(description="WS v2 add_order smoketest (validate=1)")
    p.add_argument("--pairs", default="BTC/USD,ETH/USD", help="comma-separated list of pairs")
    p.add_argument("--volume", type=float, default=0.001)
    p.add_argument("--price", type=float, default=100.0, help="limit price far away to ensure validate path")
    args = p.parse_args()

    pairs = [s.strip() for s in args.pairs.split(",") if s.strip()]
    async def runner():
        results = {}
        for pair in pairs:
            res = await run_case(pair, "buy", "limit", args.volume, args.price, 1)
            ok = (res.get("status") == "ok")
            results[pair] = {"ok": ok, "status": res.get("status"), "snippet": json.dumps(res)[:180]}
        print(json.dumps({"summary": results}, indent=2, ensure_ascii=False))

    asyncio.run(runner())

if __name__ == "__main__":
    main()

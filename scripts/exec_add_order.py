
from __future__ import annotations
import argparse, asyncio, json
from ..orders.executor import AddOrderExecutor

def main():
    ap = argparse.ArgumentParser(description="Executor live-pad: WS v2 add_order (fixed endpoint/payload)")
    ap.add_argument("--pair", required=True, help="e.g. BTC/USD")
    ap.add_argument("--side", required=True, choices=["buy","sell"])
    ap.add_argument("--ordertype", default="limit")
    ap.add_argument("--volume", type=float, required=True)
    ap.add_argument("--price", type=float)
    ap.add_argument("--tif", default="gtc")
    ap.add_argument("--post-only", type=int, default=0)
    ap.add_argument("--validate", type=int, default=1)
    ap.add_argument("--max-retries", type=int, default=5)
    ap.add_argument("--cl-ord-id")
    ap.add_argument("--userref", type=int)
    args = ap.parse_args()

    async def run():
        ex = AddOrderExecutor(max_retries=args.max_retries)
        try:
            res = await ex.add_order(
                pair=args.pair,
                side=args.side,
                ordertype=args.ordertype,
                volume=args.volume,
                price=args.price,
                tif=args.tif,
                post_only=args.post_only,
                validate=args.validate,
                client_id=args.cl_ord_id,
                userref=args.userref,
            )
            print(json.dumps(res, indent=2, ensure_ascii=False))
        finally:
            await ex.close()

    asyncio.run(run())

if __name__ == "__main__":
    main()

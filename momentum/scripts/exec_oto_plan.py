
from __future__ import annotations
import argparse, asyncio, json, os
from ..orders.orchestrator import EntrySpec, TPLeg, SLSpec, build_oto_plan, execute_plan, amend_sl_to_be

def main():
    ap = argparse.ArgumentParser(description="OTO/OCO Orchestrator + BE-move (WS v2 amend_order)")
    ap.add_argument("--app", default=os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum")
    ap.add_argument("--pair", default="BTC/USD")
    ap.add_argument("--side", default="buy", choices=["buy","sell"])
    ap.add_argument("--entry", type=float, default=25000.0)
    ap.add_argument("--qty", type=float, default=0.01)
    ap.add_argument("--tp1", type=float, default=25500.0)
    ap.add_argument("--tp1-ratio", type=float, default=0.4)
    ap.add_argument("--tp2", type=float, default=26000.0)
    ap.add_argument("--tp2-ratio", type=float, default=0.6)
    ap.add_argument("--sl", type=float, default=24500.0)
    ap.add_argument("--sl-limit", type=float, default=None)
    ap.add_argument("--be-offset", type=float, default=5.0)
    ap.add_argument("--validate", type=int, default=1)
    ap.add_argument("--execute", type=int, default=0, help="1=send to broker, 0=print only")
    ap.add_argument("--simulate-partial", type=int, default=0, help="1=simulate TP1 fill -> amend SL to BE(+offset)")
    args = ap.parse_args()

    entry = EntrySpec(pair=args.pair, side=args.side, ordertype="limit", volume=args.qty, price=args.entry, post_only=1, tif="gtc")
    tps = [TPLeg(ratio=args.tp1_ratio, price=args.tp1), TPLeg(ratio=args.tp2_ratio, price=args.tp2)]
    sl = SLSpec(price=args.sl, limit_price=args.sl_limit)

    plan = build_oto_plan(entry, tps, sl, be_offset=args.be_offset)
    print("[PLAN]"); print(json.dumps(plan, indent=2))

    if args.execute:
        res = asyncio.run(execute_plan(args.app, plan, validate=args.validate))
        print("[EXECUTE]"); print(json.dumps(res, indent=2))

    if args.simulate_partial:
        sl_clids = [l["params"]["cl_ord_id"] for l in plan["legs"] if l["kind"]=="SL"]
        if sl_clids:
            be = asyncio.run(amend_sl_to_be(args.app, entry_price=args.entry, be_offset=args.be_offset, sl_clid=sl_clids[0], sl_volume=args.qty))
            print("[BE-MOVE]"); print(json.dumps(be, indent=2))
        else:
            print("[BE-MOVE] skipped: no SL leg present")

if __name__ == "__main__":
    main()


from __future__ import annotations
import argparse, asyncio, json, os
from ..orders.orchestrator import amend_sl_to_be

def main():
    p = argparse.ArgumentParser(description="Amend SL to BE(+offset) via WS v2")
    p.add_argument("--app", default=os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum")
    p.add_argument("--entry", type=float, required=True)
    p.add_argument("--offset", type=float, default=0.0)
    p.add_argument("--clid", required=True, help="SL cl_ord_id")
    p.add_argument("--qty", type=float, required=True, help="SL volume")
    args = p.parse_args()
    res = asyncio.run(amend_sl_to_be(args.app, args.entry, args.offset, args.clid, args.qty))
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()

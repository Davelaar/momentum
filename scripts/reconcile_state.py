
from __future__ import annotations
import argparse, asyncio, json, os
from ..services.reconciliation import reconcile

def main():
    p = argparse.ArgumentParser(description="Reconcile state files from Kraken REST truth")
    p.add_argument("--app", default=os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum")
    p.add_argument("--dry-run", type=int, default=1)
    args = p.parse_args()

    diff_oo, diff_pos = asyncio.run(reconcile(args.app, dry_run=bool(args.dry_run)))
    print("[open_orders_state.json]")
    print(json.dumps(diff_oo, indent=2, ensure_ascii=False))
    print("[positions.json]")
    print(json.dumps(diff_pos, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()

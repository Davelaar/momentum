
from __future__ import annotations
import argparse, asyncio, os
from ..janitor.service import Janitor

def main():
    ap = argparse.ArgumentParser(description="Janitor run_once (null-safe, debounced, rate-limited)")
    ap.add_argument("--app", default=os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum")
    ap.add_argument("--rate", type=float, default=2.0)
    ap.add_argument("--burst", type=int, default=4)
    ap.add_argument("--debounce", type=int, default=5)
    args = ap.parse_args()

    j = Janitor(args.app, rate_per_sec=args.rate, burst=args.burst, debounce_sec=args.debounce)
    asyncio.run(j.run_once())

if __name__ == "__main__":
    main()

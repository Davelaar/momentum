import os, json, argparse, sys, asyncio
from momentum.kraken.rest_client import KrakenREST

async def _fetch_usd_balance():
    kraken = KrakenREST()
    try:
        bals = await kraken.balances()
        usd = 0.0
        for k in ("ZUSD","USD"):
            if k in bals:
                try:
                    usd += float(bals[k])
                except Exception:
                    pass
        return {"equity_usd": usd}
    finally:
        await kraken.close()

def main():
    p = argparse.ArgumentParser(description="Update local equity cache (USD cash balance)")
    p.add_argument("--out", type=str, default=None, help="Output file (defaults to $APP/var/account_equity_usd.json)")
    args = p.parse_args()
    app = os.environ.get("APP", ".")
    out = args.out or os.path.join(app, "var", "account_equity_usd.json")
    allow = os.environ.get("ALLOW_BALANCE_REST", "0") in ("1","true","yes","on","True")
    if not allow:
        print("REST disabled. Set ALLOW_BALANCE_REST=1 to enable.", file=sys.stderr)
        sys.exit(2)
    data = asyncio.get_event_loop().run_until_complete(_fetch_usd_balance())
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(json.dumps({"out": out, **data}))

if __name__ == "__main__":
    main()
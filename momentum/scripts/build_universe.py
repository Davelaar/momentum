
import os
import asyncio
import json
import argparse
from momentum.universe.fetch_universe import build_universe

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=os.environ.get("APP", "."), help="APP path (default from $APP)")
    args = ap.parse_args()
    res = asyncio.run(build_universe(app_path=args.app))
    print(json.dumps({"ok": True, **res}))

if __name__ == "__main__":
    main()


import os, asyncio, argparse
from momentum.ws.private import PrivateWSManager

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=os.environ.get("APP", "."))
    args = ap.parse_args()
    mgr = PrivateWSManager(app_path=args.app)
    asyncio.run(mgr.run())

if __name__ == "__main__":
    main()

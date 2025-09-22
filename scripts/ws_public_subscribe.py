
import os, asyncio, argparse
from momentum.ws.public import PublicWSManager

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=os.environ.get("APP", "."))
    args = ap.parse_args()
    mgr = PublicWSManager(app_path=args.app)
    asyncio.run(mgr.run())

if __name__ == "__main__":
    main()

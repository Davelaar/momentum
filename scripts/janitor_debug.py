from __future__ import annotations
import os, asyncio
from ..janitor.service import Janitor

def main():
    app = os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum"
    j = Janitor(app, rate_per_sec=10.0, burst=10, debounce_sec=0)
    print("DEBUG: invoking run_once()", flush=True)
    asyncio.run(j.run_once())
    print("DEBUG: run_once() DONE", flush=True)

if __name__ == "__main__":
    main()

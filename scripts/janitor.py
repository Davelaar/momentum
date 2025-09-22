
from __future__ import annotations
import argparse
from momentum.services.janitor import main as janitor_main

def parse_args():
    p = argparse.ArgumentParser(description="Momentum Janitor — timeout & cleanup")
    p.add_argument("--dry-run", type=int, default=1, help="1=log only (default), 0=live (noop actions)")
    p.add_argument("--loop", type=int, default=0, help="1=continuous loop (systemd), 0=single run")
    return p.parse_args()

def main():
    args = parse_args()
    janitor_main(dry_run=bool(args.dry_run), loop=bool(args.loop))

if __name__ == "__main__":
    main()

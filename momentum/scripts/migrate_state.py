
from __future__ import annotations
import argparse, os, json
from ..state.atomic_json import migrate_if_needed, read_json

def migrate_open_orders(obj: dict) -> dict:
    # v1 structure already fine; ensure plain dict without _schema
    if isinstance(obj, dict) and "_schema" in obj:
        obj = {k: v for k, v in obj.items() if k != "_schema"}
    return obj

def migrate_positions(obj: dict) -> dict:
    # v1 structure already fine; ensure keys exist
    if isinstance(obj, dict) and "_schema" in obj:
        obj = {k: v for k, v in obj.items() if k != "_schema"}
    if "positions" not in obj:
        obj = {"positions": {}, "asof": 0.0} if obj == {} else obj
    return obj

def main():
    ap = argparse.ArgumentParser(description="Mini-migrator for state JSON files")
    ap.add_argument("--app", default=os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum")
    args = ap.parse_args()

    var = f"{args.app}/var"
    oo = f"{var}/open_orders_state.json"
    ps = f"{var}/positions.json"

    changed = []
    if migrate_if_needed(oo, "open_orders_state/v1", migrate_open_orders):
        changed.append("open_orders_state.json->v1")
    if migrate_if_needed(ps, "positions_state/v1", migrate_positions):
        changed.append("positions.json->v1")

    print("Migrations:", ", ".join(changed) if changed else "none")

    # Show final schemas
    for path in (oo, ps):
        data = read_json(path)
        print(os.path.basename(path), "schema=", data.get("_schema"))

if __name__ == "__main__":
    main()

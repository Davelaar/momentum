
from __future__ import annotations
import json, os
from ..state.json_safety import read_json_dict, read_json_list

def main():
    app = os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum"
    var = os.path.join(app, "var")
    # Example of null-safe reads that Janitor should use:
    open_orders = read_json_list(os.path.join(var, "open_orders.json"))
    orders      = read_json_list(os.path.join(var, "orders.json"))
    actions     = read_json_dict(os.path.join(var, "janitor_actions.json"))
    print(json.dumps({
        "types": {
            "open_orders.json": type(open_orders).__name__,
            "orders.json": type(orders).__name__,
            "janitor_actions.json": type(actions).__name__,
        },
        "sizes": {"open_orders": len(open_orders), "orders": len(orders), "actions": len(actions)},
    }, indent=2))

if __name__ == "__main__":
    main()

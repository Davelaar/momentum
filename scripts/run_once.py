#!/usr/bin/env python3
from momentum.ranker.selector import refresh_universe, build_order_plan
from momentum.services.trader import run_once

if __name__ == "__main__":
    refresh_universe()
    plan = build_order_plan(max_notional_usd=10.0)
    print("PLAN", plan)
    run_once()
    print("OK")

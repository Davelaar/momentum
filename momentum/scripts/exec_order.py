
from __future__ import annotations

import argparse
import sys
from momentum.orders.executor import OrderExecutor, TPLeg

def parse_tp(tp_str: str, qty: float):
    """
    Parse --tp like: "25200@40%,25250@60%:25260"
    - price@pct%[:limit]
    """
    if not tp_str:
        return []
    legs = []
    for item in tp_str.split(","):
        item = item.strip()
        if not item:
            continue
        # split limit if present
        if ":" in item:
            price_part, limit_part = item.split(":", 1)
        else:
            price_part, limit_part = item, None
        # price@pct%
        price_s, pct_s = price_part.split("@", 1)
        price = float(price_s)
        pct_s = pct_s.rstrip("%")
        pct = float(pct_s)
        leg_qty = round(qty * pct / 100.0, 12)
        limit_price = float(limit_part) if limit_part else None
        legs.append(TPLeg(price=price, qty=leg_qty, limit_price=limit_price))
    return legs

def main():
    p = argparse.ArgumentParser(description="Momentum Orders Executor (dry-run)")
    p.add_argument("--symbol", required=True)
    p.add_argument("--side", required=True, choices=["buy", "sell"])
    p.add_argument("--qty", required=True, type=float)
    p.add_argument("--limit", required=True, type=float, help="Absolute limit price for entry (required)")
    p.add_argument("--tif", default="gtc", choices=["gtc", "gtd", "ioc"])
    p.add_argument("--post_only", type=int, default=1)
    p.add_argument("--validate", type=int, default=1)
    p.add_argument("--dry_run", type=int, default=1)
    p.add_argument("--sl", type=float, default=None)
    p.add_argument("--sl_limit", type=float, default=None)
    p.add_argument("--tp", type=str, default="", help='Comma list: "price@pct%[:limit]", e.g. "25200@40%,25250@60%:25255"')

    args = p.parse_args()

    # Build executor
    ex = OrderExecutor(
        symbol=args.symbol,
        side=args.side,
        qty=args.qty,
        limit_price=args.limit,
        time_in_force=args.tif,
        post_only=bool(args.post_only),
        validate=bool(args.validate),
        reference="last",
    )

    # Parse TP legs
    tp_legs = parse_tp(args.tp, args.qty)

    # Build payloads
    try:
        result = ex.build(sl=args.sl, sl_limit=args.sl_limit, tp_legs=tp_legs)
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(2)

    # Dump to var
    outp = OrderExecutor.dump_to_var(result)
    print(f"[dry-run] wrote payloads to {outp}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

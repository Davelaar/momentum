
from __future__ import annotations
import argparse, json, os
from momentum.models.intent import Intent, TakeProfitLeg
from momentum.utils.env import load_env_knobs
from momentum.utils.safety import SafetyKnobs
from momentum.exchange.kraken.ws_v2_payloads import build_primary_payload, build_standalone_tp_messages

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--side", required=True, choices=["buy","sell"])
    ap.add_argument("--qty", type=float, required=True)
    ap.add_argument("--limit", type=float)
    ap.add_argument("--tif", default=None)
    ap.add_argument("--post_only", type=int, default=0)
    ap.add_argument("--validate", type=int, default=1)
    ap.add_argument("--sl", type=float, help="OTO stop trigger (for stop-loss-limit this is trigger_price)")
    ap.add_argument("--sl_limit", type=float, help="OTO stop-loss-limit limit_price")
    ap.add_argument("--tp", type=float, help="Standalone TP trigger_price (static)")
    ap.add_argument("--tp_limit", type=float, help="Standalone TP limit_price (optional)")
    ap.add_argument("--standalone_tp", type=int, default=0)
    args = ap.parse_args()

    knobs_raw = load_env_knobs(os.environ.get("APP"))
    knobs = SafetyKnobs(
        entry_max_notional=float(knobs_raw.get("ENTRY_MAX_NOTIONAL", 10)),
        one_position_only=int(knobs_raw.get("ONE_POSITION_ONLY", 1)),
        abs_limit_required=int(knobs_raw.get("ABS_LIMIT_REQUIRED", 1)),
    )
    quote_ccy = "USD"
    intent = Intent(
        symbol=args.symbol,
        side=args.side,
        qty=args.qty,
        order_type="limit" if args.limit is not None else "market",
        limit_price=args.limit,
        tif=(args.tif or knobs_raw.get("DEFAULT_TIF","gtc")),
        post_only=bool(args.post_only),
        validate_only=bool(args.validate),
        deadline_ms=int(knobs_raw.get("DEADLINE_MS", 5000)),
    )
    if args.sl is not None:
        intent.oto_order_type = "stop-loss-limit" if args.sl_limit is not None else "stop-loss"
        intent.oto_trigger_price = args.sl
        intent.oto_limit_price = args.sl_limit

    msg = build_primary_payload(intent, quote_ccy, knobs, token_placeholder="TOKEN_REDACTED")
    out = [msg.model_dump()]

    if args.standalone_tp and args.tp is not None:
        leg = TakeProfitLeg(trigger_price=args.tp, limit_price=args.tp_limit, pct_size=1.0)
        tps = build_standalone_tp_messages(args.symbol, "sell" if args.side=="buy" else "buy", args.qty, [leg], quote_ccy, knobs, token_placeholder="TOKEN_REDACTED")
        out.extend([m.model_dump() for m in tps])

    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()

import argparse, os, sys, shlex, subprocess, json
from momentum.utils.risk_sizing import load_knobs_from_env, read_equity_usd, compute_qty
def main():
    ap = argparse.ArgumentParser(description="E2E dryrun (risk-sized wrapper)")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--symbols", type=str, default="")
    ap.add_argument("--symbol", type=str, default="")
    ap.add_argument("--rank", type=str, default="spread")
    ap.add_argument("--spread_window_s", type=int, default=60)
    ap.add_argument("--min_top_size", type=int, default=3)
    ap.add_argument("--min_quote_band_usd", type=float, default=10.0)
    ap.add_argument("--qty", type=float, default=None)
    ap.add_argument("--limit", type=float, required=True)
    ap.add_argument("--tp", type=str, default="0.009:50,0.014:30,0.021:20")
    ap.add_argument("--sl", type=str, default="0.010")
    ap.add_argument("--breakeven", type=int, default=1)
    ap.add_argument("--breakeven_offset_pct", type=float, default=0.001)
    ap.add_argument("--tif", type=str, default="gtc")
    ap.add_argument("--post_only", type=int, default=1)
    ap.add_argument("--validate_only", type=int, default=1)
    ap.add_argument("--output-dir", type=str, default=None)
    args = ap.parse_args()
    qty = args.qty
    extra_meta = {}
    if qty is None:
        knobs = load_knobs_from_env()
        eq = read_equity_usd(knobs)
        res = compute_qty(args.limit, eq, knobs.get("ENTRY_RISK_PCT"), knobs.get("ENTRY_MAX_NOTIONAL"), knobs.get("ENTRY_MIN_NOTIONAL"))
        qty = res["final_qty"]
        extra_meta = res
    cmd = [sys.executable, "-m", "momentum.scripts.e2e_sim_dryrun",
        "--rank", args.rank, "--spread_window_s", str(args.spread_window_s),
        "--min_top_size", str(args.min_top_size), "--min_quote_band_usd", str(args.min_quote_band_usd),
        "--qty", str(qty), "--limit", str(args.limit),
        "--tp", args.tp, "--sl", args.sl,
        "--breakeven", str(args.breakeven), "--breakeven_offset_pct", str(args.breakeven_offset_pct),
        "--tif", args.tif, "--post_only", str(args.post_only),
        "--validate_only", str(args.validate_only)]
    if args.output_dir: cmd += ["--output-dir", args.output_dir]
    if args.symbols: cmd += ["--symbols", args.symbols]
    if args.symbol: cmd += ["--symbol", args.symbol]
    if args.top: cmd += ["--top", str(args.top)]
    print(json.dumps({"risk_sizing": extra_meta, "exec": " ".join(shlex.quote(x) for x in cmd)}))
    sys.exit(subprocess.call(cmd))
if __name__ == "__main__":
    main()
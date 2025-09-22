import argparse, os, sys, shlex, subprocess, json
from momentum.utils.risk_sizing import load_knobs_from_env, read_equity_usd, compute_qty
def main():
    p = argparse.ArgumentParser(description="Momentum E2E LIVE (risk-sized wrapper)")
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--symbols", type=str, default="")
    p.add_argument("--symbol", type=str, default="")
    p.add_argument("--rank", type=str, default="spread")
    p.add_argument("--spread_window_s", type=int, default=60)
    p.add_argument("--min_top_size", type=int, default=3)
    p.add_argument("--min_quote_band_usd", type=float, default=10.0)
    p.add_argument("--qty", type=float, default=None)
    p.add_argument("--limit", type=float, default=29000.0)
    p.add_argument("--tp", type=str, default="0.009:50,0.014:30,0.021:20")
    p.add_argument("--sl", type=str, default="0.010")
    p.add_argument("--breakeven", type=int, default=1)
    p.add_argument("--breakeven_offset_pct", type=float, default=0.001)
    p.add_argument("--tif", type=str, default="gtc")
    p.add_argument("--post_only", type=int, default=1)
    p.add_argument("--output-dir", type=str, default=os.path.join(os.environ.get("APP","."),"var","e2e_runs_live"))
    args = p.parse_args()
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
        "--validate_only", "0", "--output-dir", args.output_dir]
    if args.symbols: cmd += ["--symbols", args.symbols]
    if args.symbol: cmd += ["--symbol", args.symbol]
    if args.top: cmd += ["--top", str(args.top)]
    print(json.dumps({"risk_sizing": extra_meta, "exec": " ".join(shlex.quote(x) for x in cmd)}))
    sys.exit(subprocess.call(cmd))
if __name__ == "__main__":
    main()
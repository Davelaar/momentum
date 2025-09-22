
import argparse, os, sys, shlex, subprocess, json

from momentum.utils.risk_sizing import load_knobs_from_env, read_equity_usd, compute_qty
from momentum.utils.price_feed import mids_sync
from momentum.utils.specs_sync import specs_sync

def _ceil_to_tick(x: float, tick: float) -> float:
    if tick <= 0: return x
    n = int((x + 1e-15) / tick)
    if n * tick < x - 1e-15:
        n += 1
    return round(n * tick, 12)

def _floor_to_step(x: float, step: float) -> float:
    if step <= 0: return x
    n = int((x + 1e-15) / step)
    return round(n * step, 12)

def main():
    p = argparse.ArgumentParser(description="Momentum E2E LIVE (risk-sized, strict cap vs tick/lot, auto-limit)")
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--symbols", type=str, default="")
    p.add_argument("--symbol", type=str, default="")
    p.add_argument("--rank", type=str, default="spread")
    p.add_argument("--spread_window_s", type=int, default=60)
    p.add_argument("--min_top_size", type=int, default=3)
    p.add_argument("--min_quote_band_usd", type=float, default=10.0)
    p.add_argument("--qty", type=float, default=None)
    p.add_argument("--limit", type=float, default=None)
    p.add_argument("--tp", type=str, default="0.009:50,0.014:30,0.021:20")
    p.add_argument("--sl", type=str, default="0.010")
    p.add_argument("--breakeven", type=int, default=1)
    p.add_argument("--breakeven_offset_pct", type=float, default=0.001)
    p.add_argument("--tif", type=str, default="gtc")
    p.add_argument("--post_only", type=int, default=1)
    p.add_argument("--output-dir", type=str, default=os.path.join(os.environ.get("APP","."),"var","e2e_runs_live"))
    args = p.parse_args()

    knobs = load_knobs_from_env()
    qty = args.qty
    limit_price = args.limit
    meta = {"env_driven": True}

    # Determine symbols list
    wss = []
    if args.symbols:
        wss = [s for s in args.symbols.split(",") if s]
    elif args.symbol:
        wss = [args.symbol]

    # auto-limit
    limit_src = str(knobs.get("ENTRY_LIMIT_SOURCE", "fixed")).lower()
    limit_off = float(knobs.get("ENTRY_LIMIT_OFFSET_PCT") or 0.0)
    if (limit_price is None) or (limit_src == "auto"):
        mids = mids_sync(wss) if wss else {}
        vals = sorted([v for v in mids.values() if v > 0])
        if vals:
            base = vals[len(vals)//2]
            limit_price = base * (1.0 + limit_off)
            meta["limit_base_mid"] = base
            meta["limit_offset_pct"] = limit_off
            meta["limit_chosen"] = limit_price

    # strict notional cap vs rounding
    specs = specs_sync(wss) if wss else {}
    eff_limits = []
    vol_steps = []
    for ws in wss:
        price_tick, vol_step = specs.get(ws, (0.0, 0.0))
        eff_limits.append(_ceil_to_tick(limit_price, price_tick) if limit_price else None)
        if vol_step:
            vol_steps.append(vol_step)
    effective_limit = max([x for x in eff_limits if x], default=limit_price or 0.0)
    min_vol_step = max(vol_steps) if vol_steps else 0.0

    if qty is None:
        eq = read_equity_usd(knobs)
        base = compute_qty(
            limit_price=limit_price,
            equity_usd=eq,
            risk_pct=knobs.get("ENTRY_RISK_PCT"),
            max_notional=knobs.get("ENTRY_MAX_NOTIONAL"),
            min_notional=knobs.get("ENTRY_MIN_NOTIONAL"),
        )
        qty = base["final_qty"]
        max_notional = knobs.get("ENTRY_MAX_NOTIONAL")
        if max_notional not in (None, 0, 0.0):
            cap_qty = max_notional / (effective_limit if effective_limit else limit_price)
            if min_vol_step:
                cap_qty = _floor_to_step(cap_qty, min_vol_step)
            if cap_qty < qty:
                qty = cap_qty
                base["caps_applied"] = list(set((base.get("caps_applied") or []) + ["tick/lot_strict"]))
        meta["risk_sizing"] = base
        meta["effective_limit_worst"] = effective_limit
        meta["min_vol_step"] = min_vol_step

    cmd = [
        sys.executable, "-m", "momentum.scripts.e2e_sim_dryrun",
        "--rank", args.rank,
        "--spread_window_s", str(args.spread_window_s),
        "--min_top_size", str(args.min_top_size),
        "--min_quote_band_usd", str(args.min_quote_band_usd),
        "--qty", str(qty),
        "--limit", str(limit_price),
        "--tp", args.tp,
        "--sl", args.sl,
        "--breakeven", str(args.breakeven),
        "--breakeven_offset_pct", str(args.breakeven_offset_pct),
        "--tif", args.tif,
        "--post_only", str(args.post_only),
        "--validate_only", "0",
        "--output-dir", args.output_dir,
    ]
    if args.symbols:
        cmd += ["--symbols", args.symbols]
    if args.symbol:
        cmd += ["--symbol", args.symbol]
    if args.top:
        cmd += ["--top", str(args.top)]

    print(json.dumps({"wrapper_meta": meta, "exec": " ".join(shlex.quote(x) for x in cmd)}))
    sys.exit(subprocess.call(cmd))

if __name__ == "__main__":
    main()

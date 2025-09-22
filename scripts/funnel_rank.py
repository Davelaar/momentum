from __future__ import annotations
import os, json, argparse, asyncio, pathlib, csv
from typing import List, Dict, Any
from momentum.funnel.io import atomic_write_json, ensure_dir
from momentum.funnel.filters import Pair, filter_fiat_and_stables, apply_liquidity_filters, apply_anomaly_filters
from momentum.funnel.metrics import compute_short_term_vol, enrich_liquidity, enrich_spread, compute_momentum_signals, compute_spread_atr_ratio
from momentum.funnel.tactics import assign_and_score

APP = os.environ.get("APP", os.getcwd())

def read_universe(path: str) -> List[Pair]:
    with open(path, 'r') as f:
        data = json.load(f)
    pairs = []
    for entry in data if isinstance(data, list) else data.get("pairs", []):
        # accept {'pair': 'BTC/USD'} or {'wsname':'BTC/USD'}
        sym = entry.get("pair") or entry.get("wsname") or entry.get("symbol")
        if not sym: 
            continue
        if not sym.endswith("/USD"):
            continue
        base, quote = sym.split("/")
        pairs.append(Pair(symbol=sym, base=base, quote=quote))
    return pairs

def write_csv(path: str, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

def stage_vol(args):
    top = int(os.environ.get("FUNNEL_TOP_N", args.top or 100))
    uni_path = os.path.join(APP, "var", "universe.json")
    pairs = read_universe(uni_path)
    pairs = filter_fiat_and_stables(pairs)
    atomic_write_json(os.path.join(APP, "var/funnel/step0_universe_filtered.json"), [p.__dict__ for p in pairs])
    pair_syms = [p.symbol for p in pairs]
    rows = asyncio.run(compute_short_term_vol(pair_syms, top_n=top))
    atomic_write_json(os.path.join(APP, "var/funnel/step1_topN_vol.json"), rows)

def stage_liq(args):
    path = os.path.join(APP, "var/funnel/step1_topN_vol.json")
    if not os.path.exists(path):
        raise SystemExit("Run --stage vol first.")
    rows = json.load(open(path))
    rows = asyncio.run(enrich_liquidity(rows))
    min_vol = float(os.environ.get("LIQ_MIN_VOL24H_USD", 1_000_000))
    rows = apply_liquidity_filters(rows, min_vol24h_usd=min_vol)
    atomic_write_json(os.path.join(APP, "var/funnel/step2_liquid.json"), rows)

def stage_spread(args):
    path = os.path.join(APP, "var/funnel/step2_liquid.json")
    if not os.path.exists(path):
        raise SystemExit("Run --stage liq first.")
    rows = json.load(open(path))
    rows = asyncio.run(enrich_spread(rows))
    max_spread = float(os.environ.get("MAX_SPREAD_PCT", 0.15))
    rows = [r for r in rows if r.get("spread_pct") is not None and r["spread_pct"] <= max_spread]
    atomic_write_json(os.path.join(APP, "var/funnel/step3_spread.json"), rows)

def stage_momentum(args):
    path = os.path.join(APP, "var/funnel/step3_spread.json")
    if not os.path.exists(path):
        raise SystemExit("Run --stage spread first.")
    rows = json.load(open(path))
    # For now we reuse 15m closes via a light fetch; optimization later.
    # Placeholder: we don't persist series; tactics is robust to missing data.
    # (A later step can add a series cache if needed.)
    # No additional fetch here; compute_momentum_signals requires closes_5m
    closes = {r["symbol"]: [] for r in rows}
    rows = compute_momentum_signals(rows, closes_5m=closes)
    atomic_write_json(os.path.join(APP, "var/funnel/step4_momentum.json"), rows)

def stage_final(args):
    path = os.path.join(APP, "var/funnel/step4_momentum.json")
    if not os.path.exists(path):
        raise SystemExit("Run --stage momentum first.")
    rows = json.load(open(path))
    rows2 = assign_and_score(rows)
    outj = {
        "asof": __import__("datetime").datetime.utcnow().isoformat()+"Z",
        "universe_size": len(json.load(open(os.path.join(APP,"var/funnel/step0_universe_filtered.json")))),
        "candidates": len(rows2),
        "results": rows2
    }
    out_json = os.path.join(APP, "var/funnel/selection.json")
    atomic_write_json(out_json, outj)
    # CSV
    out_csv = os.path.join(APP, "var/funnel/selection.csv")
    fields = ["symbol","score","tactic","pct_change_15m","pct_change_1h","vol24h_usd","spread_pct","rsi_15m","ema8_gt_ema21","atr","spread_atr_ratio"]
    write_csv(out_csv, rows2, fields)

def main():
    ap = argparse.ArgumentParser(description="Momentum Funnel Ranker (additive, dry-run)")
    ap.add_argument("--stage", required=True, choices=["vol","liq","spread","momentum","final"])
    ap.add_argument("--top", type=int, help="Top N (volatility)")
    args = ap.parse_args()
    pathlib.Path(os.path.join(APP,"var/funnel")).mkdir(parents=True, exist_ok=True)
    match args.stage:
        case "vol": stage_vol(args)
        case "liq": stage_liq(args)
        case "spread": stage_spread(args)
        case "momentum": stage_momentum(args)
        case "final": stage_final(args)

if __name__ == "__main__":
    main()

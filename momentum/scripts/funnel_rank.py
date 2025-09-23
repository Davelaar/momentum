from __future__ import annotations
import os, json, argparse, asyncio, pathlib, csv
from typing import List, Dict, Any
from momentum.funnel.io import atomic_write_json, ensure_dir
from momentum.funnel.filters import Pair, filter_fiat_and_stables, apply_liquidity_filters, apply_anomaly_filters
from momentum.funnel.metrics import compute_short_term_vol, enrich_liquidity, enrich_spread, compute_momentum_signals, compute_spread_atr_ratio

APP = os.environ.get("APP", os.getcwd())

def _normalize_symbol(sym: str | None) -> str | None:
    if not sym:
        return None
    s = str(sym).strip()
    if "/" not in s and s.upper().endswith("USD"):
        return f"{s[:-3]}/USD"
    return s if "/" in s else None

def _extract_items(obj: Any) -> list:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        items = obj.get("universe") or obj.get("pairs") or obj.get("result") or []
        if isinstance(items, dict):
            flat = []
            for v in items.values():
                if isinstance(v, list):
                    flat.extend(v)
            return flat
        return items if isinstance(items, list) else []
    return []

def read_universe(path: str) -> List[Pair]:
    with open(path, 'r') as f:
        data = json.load(f)
    items = _extract_items(data)
    pairs: List[Pair] = []
    for e in items:
        sym = None
        if isinstance(e, dict):
            sym = e.get("wsname") or e.get("pair") or e.get("symbol") or e.get("altname") or e.get("name")
        elif isinstance(e, str):
            sym = e
        sym = _normalize_symbol(sym)
        if not sym or not sym.endswith("/USD"):
            continue
        try:
            base, quote = sym.split("/", 1)
        except ValueError:
            continue
        pairs.append(Pair(symbol=sym, base=base, quote=quote))
    return pairs

def write_csv(path: str, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    ensure_dir(path)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

def _to_float_env(name: str, default: float) -> float:
    v = os.environ.get(name)
    try:
        return float(v) if v is not None else default
    except Exception:
        return default

def _read_equity_usd_safe(app_path: str) -> float:
    # 1) Try the library function with app_path
    try:
        from momentum.utils import risk_sizing as _rs
        try:
            eq = _rs.read_equity_usd(app_path)  # may expect app path
            if isinstance(eq, (int, float)) and eq >= 0:
                return float(eq)
        except TypeError:
            # 2) Try without args (some variants take none)
            eq = _rs.read_equity_usd()
            if isinstance(eq, (int, float)) and eq >= 0:
                return float(eq)
    except Exception:
        pass
    # 3) Try reading the cache file directly
    try:
        p = os.path.join(app_path, "var", "account_equity_usd.json")
        with open(p, "r") as f:
            data = json.load(f)
        # accept shapes: {"equity_usd": 123.45} or just a number
        if isinstance(data, dict) and "equity_usd" in data:
            return float(data["equity_usd"] or 0.0)
        if isinstance(data, (int, float)):
            return float(data)
    except Exception:
        pass
    # 4) Fallback
    return 0.0

def _compute_dynamic_liq_threshold(app_path: str) -> Dict[str, float]:
    dyn_enabled = int(os.environ.get("LIQ_VOL_DYNAMIC", "1")) == 1
    static_env = os.environ.get("LIQ_MIN_VOL24H_USD")

    equity = _read_equity_usd_safe(app_path)
    entry_notional = _to_float_env("ENTRY_NOTIONAL_USD", 10.0)

    min_floor = _to_float_env("LIQ_VOL_MIN_FLOOR", 100_000.0)
    mult_eq   = _to_float_env("LIQ_VOL_EQUITY_MULT", 700.0)
    mult_not  = _to_float_env("LIQ_VOL_NOTIONAL_MULT", 10_000.0)

    dyn_val = max(min_floor, equity * mult_eq, entry_notional * mult_not)
    if static_env is not None:
        try:
            dyn_val = max(dyn_val, float(static_env))
        except Exception:
            pass

    if not dyn_enabled:
        final_val = _to_float_env("LIQ_MIN_VOL24H_USD", 1_000_000.0)
    else:
        final_val = dyn_val

    return {
        "equity_usd": float(equity),
        "entry_notional_usd": float(entry_notional),
        "min_floor": float(min_floor),
        "equity_mult": float(mult_eq),
        "notional_mult": float(mult_not),
        "static_env": float(static_env) if (static_env and static_env.replace('.','',1).isdigit()) else None,
        "dynamic_enabled": bool(dyn_enabled),
        "min_vol24h_usd": float(final_val),
    }

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

    params = _compute_dynamic_liq_threshold(APP)
    ensure_dir(os.path.join(APP, "var/funnel/liq_params.json"))
    atomic_write_json(os.path.join(APP, "var/funnel/liq_params.json"), params)
    min_vol = params["min_vol24h_usd"]

    rows = asyncio.run(enrich_liquidity(rows))
    rows = apply_liquidity_filters(rows, min_vol24h_usd=min_vol)
    atomic_write_json(os.path.join(APP, "var/funnel/step2_liquid.json"), rows)

def stage_spread(args):
    path = os.path.join(APP, "var/funnel/step2_liquid.json")
    if not os.path.exists(path):
        raise SystemExit("Run --stage liq first.")
    rows = json.load(open(path))
    rows = asyncio.run(enrich_spread(rows))
    max_spread = float(os.environ.get("MAX_SPREAD_PCT", 0.30))
    rows = [r for r in rows if r.get("spread_pct") is not None and r["spread_pct"] <= max_spread]
    atomic_write_json(os.path.join(APP, "var/funnel/step3_spread.json"), rows)

def stage_momentum(args):
    path = os.path.join(APP, "var/funnel/step3_spread.json")
    if not os.path.exists(path):
        raise SystemExit("Run --stage spread first.")
    rows = json.load(open(path))
    rows = compute_momentum_signals(rows, closes_5m=None)
    atomic_write_json(os.path.join(APP, "var/funnel/step4_momentum.json"), rows)

def stage_final(args):
    path = os.path.join(APP, "var/funnel/step4_momentum.json")
    if not os.path.exists(path):
        raise SystemExit("Run --stage momentum first.")
    rows = json.load(open(path))
    from momentum.funnel.tactics import assign_and_score
    rows2 = assign_and_score(rows)
    outj = {
        "asof": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "universe_size": len(json.load(open(os.path.join(APP,"var/funnel/step0_universe_filtered.json")))),
        "candidates": len(rows2),
        "results": rows2
    }
    out_json = os.path.join(APP, "var/funnel/selection.json")
    atomic_write_json(out_json, outj)
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
# === APPEND-ONLY: RIGHT-SIDE-OF-CANDLE GATE (EARLY FILTER) ==============================
from momentum.funnel.metrics import is_right_side_of_candle as _rs_gate

def _early_right_side_filter(rows):
    ok_rows, skipped = [], []
    for r in rows:
        try:
            ok, reason = _rs_gate(r)
        except Exception as e:
            ok, reason = False, f"gate_error:{e}"
        if ok:
            ok_rows.append(r)
        else:
            rr = dict(r); rr.setdefault("meta", {})
            rr["meta"]["right_side_reason"] = reason
            rr["tactic"] = "SKIP"; rr["score"] = 0.0
            skipped.append(rr)
    return ok_rows, skipped

_prev_stage_momentum = globals().get("stage_momentum")

def stage_momentum(args):
    produced = None
    if callable(_prev_stage_momentum):
        produced = _prev_stage_momentum(args)
    import json, os, pathlib
    app = os.environ.get("APP", ".")
    step4 = pathlib.Path(app) / "var" / "funnel" / "step4_momentum.json"
    if produced is None and not step4.exists():
        return produced
    try:
        rows = json.loads(step4.read_text(encoding="utf-8"))
        rows = [r for r in rows if isinstance(r, dict)]
    except Exception:
        return produced
    keep, reject = _early_right_side_filter(rows)
    step4.write_text(json.dumps(keep, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    rej_path = step4.with_name("step4_momentum_rejected_rightside.json")
    try:
        rej_path.write_text(json.dumps(reject, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return produced
# ========================================================================================
# === APPEND-ONLY: RIGHT-SIDE-OF-CANDLE GATE (EARLY FILTER) ==============================
from momentum.funnel.metrics import is_right_side_of_candle as _rs_gate

def _early_right_side_filter(rows):
    ok_rows, skipped = [], []
    for r in rows:
        try:
            ok, reason = _rs_gate(r)
        except Exception as e:
            ok, reason = False, f"gate_error:{e}"
        if ok:
            ok_rows.append(r)
        else:
            rr = dict(r); rr.setdefault("meta", {})
            rr["meta"]["right_side_reason"] = reason
            rr["tactic"] = "SKIP"; rr["score"] = 0.0
            skipped.append(rr)
    return ok_rows, skipped

_prev_stage_momentum = globals().get("stage_momentum")

def stage_momentum(args):
    produced = None
    if callable(_prev_stage_momentum):
        produced = _prev_stage_momentum(args)
    import json, os, pathlib
    app = os.environ.get("APP", ".")
    step4 = pathlib.Path(app) / "var" / "funnel" / "step4_momentum.json"
    if produced is None and not step4.exists():
        return produced
    try:
        rows = json.loads(step4.read_text(encoding="utf-8"))
        rows = [r for r in rows if isinstance(r, dict)]
    except Exception:
        return produced
    keep, reject = _early_right_side_filter(rows)
    step4.write_text(json.dumps(keep, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    rej_path = step4.with_name("step4_momentum_rejected_rightside.json")
    try:
        rej_path.write_text(json.dumps(reject, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return produced
# ========================================================================================

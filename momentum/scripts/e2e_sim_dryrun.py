from __future__ import annotations
import os, json, argparse, pathlib, statistics, math, time, sys
from typing import List, Dict, Any
from ._e2e_helpers import (
    APP, write_json, append_ndjson, now_ts,
    load_pair_rules, get_decimals, round_price, round_qty, load_env_meanrev, to_float
)


def _safe_get_pair(row):
    if isinstance(row, str):
        return row
    if isinstance(row, dict):
        return _safe_get_pair(row)
    return None

# --- Try to import existing project modules if available ---
try:
    from momentum.funnel import rank_and_select as funnel_rank
except Exception:
    funnel_rank = None

try:
    from momentum.orders import payloads as order_payloads  # expected existing module
except Exception:
    order_payloads = None

def parse_tp_schema(s: str):
    # "0.9:50,1.4:30,2.1:20" -> list of (pct, alloc)
    parts = []
    for item in s.split(","):
        item = item.strip()
        if not item:
            continue
        pct_s, alloc_s = item.split(":")
        parts.append((float(pct_s), float(alloc_s)))
    total_alloc = sum(a for _, a in parts)
    if abs(total_alloc - 100.0) > 1e-6:
        # normalize to 100
        parts = [(p, a * 100.0 / total_alloc) for p, a in parts]
    return parts

def load_universe():
    p = pathlib.Path(APP) / "var" / "universe.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def estimate_spread_from_ws(window_s: int = 60):
    """
    Try to read a rolling median spread% per pair from a known WS artifact.
    We check a few possible files; first hit wins.
    Expected formats (flexible):
    - JSON dict: { "BTC/USD": {"median_spread_pct_60s": 0.02, "bid":..., "ask":...}, ... }
    - NDJSON with lines: {"pair":"BTC/USD","spread_pct":0.02,"window_s":60,...}
    """
    candidates = [
        pathlib.Path(APP) / "var" / "public_ws_spread_median.json",
        pathlib.Path(APP) / "var" / "public_ws_tob_spread_median.json",
        pathlib.Path(APP) / "var" / "public_ws_spread.ndjson",
    ]
    out = {}
    for path in candidates:
        if not path.exists():
            continue
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                # accept both dict[str]->obj and list[obj]
                if isinstance(data, dict):
                    for pair, obj in data.items():
                        v = obj.get("median_spread_pct_60s") or obj.get("spread_pct")
                        if v is not None:
                            out[pair] = float(v)
                elif isinstance(data, list):
                    for obj in data:
                        pair = obj.get("pair")
                        v = obj.get("median_spread_pct_60s") or obj.get("spread_pct")
                        if pair and v is not None:
                            out[pair] = float(v)
            except Exception:
                continue
        else:
            # NDJSON
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                tmp = {}
                for line in lines:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get("window_s") and int(obj["window_s"]) != window_s:
                        continue
                    pair = obj.get("pair")
                    v = obj.get("median_spread_pct_60s") or obj.get("spread_pct")
                    if pair and v is not None:
                        tmp.setdefault(pair, []).append(float(v))
                for pair, vals in tmp.items():
                    out[pair] = statistics.median(vals)
            except Exception:
                continue
        if out:
            break
    return out  # dict pair -> spread_pct

def rank_pairs_spread(top: int, window_s: int, min_top_size: float | None, min_quote_band_usd: float | None):
    ws_spreads = estimate_spread_from_ws(window_s=window_s)
    uni = load_universe()
    # Build a working map with fallback spreads
    spreads = {}
    for row in uni:
        pair = _safe_get_pair(row)
        if not pair:
            continue
        v = ws_spreads.get(pair)
        if v is None:
            v = row.get("spread_pct")
        if v is None:
            # no info -> skip later by setting +inf
            v = float("inf")
        spreads[pair] = float(v)

    # Liquidity filter placeholders (best effort; require WS/uni extras)
    # For now we use universe depth_quote_band if present vs min_quote_band_usd
    filtered = []
    for pair, sp in spreads.items():
        liq_ok = True
        reason = None
        if math.isinf(sp):
            liq_ok = False
            reason = "no_spread_data"
        # quote band check
        if liq_ok and min_quote_band_usd is not None:
            # universe.json optional field
            uni_row = next((r for r in uni if (r.get("pair") or r.get("wsname") or r.get("symbol")) == pair), None)
            band = None
            if uni_row:
                band = uni_row.get("depth_quote_band")
            if band is not None and float(band) < float(min_quote_band_usd):
                liq_ok = False
                reason = f"quote_band<{min_quote_band_usd}"
        # best_top_size check is skipped unless we have WS sizes; placeholder only
        if liq_ok and min_top_size is not None:
            # Without TOB sizes, we can't enforce; keep liq_ok True but record absence
            pass
        filtered.append((pair, sp, liq_ok, reason))

    # Sort by spread asc; ties remain stable
    filtered.sort(key=lambda x: (x[1], x[0]))
    # Keep top N liq_ok True
    ranked = [r for r in filtered if r[2]]
    return ranked[:top], filtered

def build_add_order_payload(pair: str, side: str, ordertype: str, price: float, volume: float,
                            tif: str, post_only: bool, validate: bool, cl_id: str) -> Dict[str, Any]:
    params = {
        "pair": pair,
        "side": side,
        "ordertype": ordertype,
        "timeinforce": tif.upper(),
        "post_only": bool(int(post_only)),
        "validate": bool(int(validate)),
        "cl_ord_id": cl_id,
    }
    if ordertype == "limit":
        params["price"] = f"{price:.10f}".rstrip("0").rstrip(".")
    else:
        # stop-loss / stop-loss-limit: Kraken expects 'price' (trigger) and optional 'price2' (limit)
        params["price"] = f"{price:.10f}".rstrip("0").rstrip(".")
    params["volume"] = f"{volume:.10f}".rstrip("0").rstrip(".")
    # If project has a canonical builder, delegate
    if order_payloads:
        try:
            return order_payloads.build_add_order(params)  # hypothetical; else fall back
        except Exception:
            pass
    return {"method": "add_order", "params": params}

def main():
    ap = argparse.ArgumentParser(description="Momentum E2E simulatie (dry-run) — batch top-N laagste spread")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--symbols", type=str, default="")
    ap.add_argument("--symbol", type=str, default="")
    ap.add_argument("--rank", type=str, default="spread", choices=["spread"])
    ap.add_argument("--spread_window_s", type=int, default=60)
    ap.add_argument("--min_top_size", type=float, default=None)
    ap.add_argument("--min_quote_band_usd", type=float, default=None)
    ap.add_argument("--qty", type=float, required=True)
    ap.add_argument("--limit", type=float, required=True)
    ap.add_argument("--tp", type=str, default="0.9:50,1.4:30,2.1:20")
    ap.add_argument("--sl", type=str, default="-0.5")
    ap.add_argument("--breakeven", type=int, default=1)
    ap.add_argument("--breakeven_offset_pct", type=float, default=None)
    ap.add_argument("--tif", type=str, default=None)
    ap.add_argument("--post_only", type=int, default=None)
    ap.add_argument("--validate_only", type=int, default=1)
    ap.add_argument("--output-dir", type=str, required=True)
    args = ap.parse_args()

    out_dir = pathlib.Path(APP) / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load env/config defaults
    env = load_env_meanrev()
    ENTRY_MAX_NOTIONAL = to_float(env.get("ENTRY_MAX_NOTIONAL"), None)
    DEFAULT_TIF = args.tif or env.get("DEFAULT_TIF", "GTC")
    DEFAULT_POST_ONLY = int(args.post_only if args.post_only is not None else int(env.get("DEFAULT_POST_ONLY", "1")))
    JANITOR_CLOSE_ORDER_TYPE = env.get("JANITOR_CLOSE_ORDER_TYPE", "stop-loss").lower()
    JANITOR_CLOSE_TIF = env.get("JANITOR_CLOSE_TIF", "GTC")
    BE_OFFSET = args.breakeven_offset_pct
    if BE_OFFSET is None:
        BE_OFFSET = to_float(env.get("BREAKEVEN_OFFSET_PCT"), 0.0)

    rules = load_pair_rules()

    # Resolve pair list
    pairs = []
    if args.symbols:
        pairs = [p.strip() for p in args.symbols.split(",") if p.strip()]
    elif args.symbol:
        pairs = [args.symbol.strip()]
    else:
        if args.rank == "spread":
            ranked, _all = rank_pairs_spread(args.top, args.spread_window_s, args.min_top_size, args.min_quote_band_usd)
            pairs = [p for (p, _sp, _ok, _reason) in ranked]
        else:
            pairs = []

    # If still empty and we have funnel_rank, fall back to top_n
    if not pairs and funnel_rank and hasattr(funnel_rank, "top_n"):
        try:
            pairs = funnel_rank.top_n(args.top)
        except Exception:
            pass

    # Build TP schema
    tp_schema = parse_tp_schema(args.tp)
    sl_pct = float(args.sl)

    summary_path = out_dir / "summary.ndjson"
    report = {
        "ts": now_ts(),
        "pairs_total": len(pairs),
        "ok_count": 0,
        "rejected_count": 0,
        "reasons_hist": {},
        "params": {
            "rank": args.rank,
            "top": args.top,
            "window_s": args.spread_window_s,
            "qty": args.qty,
            "limit": args.limit,
            "tp": args.tp,
            "sl": args.sl,
            "breakeven": args.breakeven,
            "breakeven_offset_pct": BE_OFFSET,
            "tif": DEFAULT_TIF,
            "post_only": DEFAULT_POST_ONLY,
            "validate_only": args.validate_only,
        }
    }

    # Metrics sink (lightweight)
    metrics_dir = pathlib.Path(APP) / "var" / "metrics.d"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = metrics_dir / "e2e_sim.prom"
    metrics_ok = 0
    metrics_rej = 0

    for idx, pair in enumerate(pairs, 1):
        price_dec, qty_dec = get_decimals(pair, rules)
        entry_price = round_price(float(args.limit), price_dec)
        total_qty = round_qty(float(args.qty), qty_dec)

        # Guard: ENTRY_MAX_NOTIONAL
        reject_reason = None
        if ENTRY_MAX_NOTIONAL is not None:
            notional = entry_price * total_qty
            if notional > ENTRY_MAX_NOTIONAL + 1e-12:
                reject_reason = f"entry_max_notional_exceeded:{notional:.8f}>{ENTRY_MAX_NOTIONAL:.8f}"

        # Split TP legs
        legs = []
        if not reject_reason:
            remaining_qty = total_qty
            for i, (tp_pct, alloc_pct) in enumerate(tp_schema, 1):
                leg_qty_raw = total_qty * (alloc_pct / 100.0)
                leg_qty = round_qty(leg_qty_raw, qty_dec)
                # ensure we don't exceed remaining due to rounding
                if leg_qty > remaining_qty:
                    leg_qty = remaining_qty
                # avoid dust legs
                if leg_qty <= 0:
                    continue
                remaining_qty = round_qty(remaining_qty - leg_qty, qty_dec)
                tp_price = round_price(entry_price * (1.0 + tp_pct / 100.0), price_dec)
                legs.append({
                    "idx": i, "tp_pct": tp_pct, "alloc_pct": alloc_pct,
                    "price": tp_price, "qty": leg_qty
                })
            # Merge dust into last leg if remainder left
            if remaining_qty > 0 and legs:
                legs[-1]["qty"] = round_qty(legs[-1]["qty"] + remaining_qty, qty_dec)
                remaining_qty = 0.0
            if not legs:
                reject_reason = "all_tp_legs_became_zero_after_rounding"

        # Build payloads
        plan = {
            "ts": now_ts(),
            "pair": pair,
            "entry": {"price": entry_price, "qty": total_qty, "tif": DEFAULT_TIF, "post_only": DEFAULT_POST_ONLY},
            "tp_legs": [],
            "sl": None,
            "breakeven": {"enabled": bool(args.breakeven), "offset_pct": BE_OFFSET, "hypothetical_amend_payload": None},
            "guards": {"ENTRY_MAX_NOTIONAL": ENTRY_MAX_NOTIONAL},
            "guards_passed": reject_reason is None
        }

        if reject_reason:
            plan["status"] = "rejected"
            plan["reject_reason"] = reject_reason
            write_json(out_dir / f"{pair.replace('/', '_')}.plan.json", plan)
            append_ndjson(summary_path, {
                "pair": pair, "guards_passed": False, "reject_reason": reject_reason
            })
            metrics_rej += 1
            report["rejected_count"] += 1
            report["reasons_hist"][reject_reason] = report["reasons_hist"].get(reject_reason, 0) + 1
            continue

        # Entry BUY limit (validate only)
        entry_payload = build_add_order_payload(
            pair=pair, side="buy", ordertype="limit", price=entry_price, volume=total_qty,
            tif=DEFAULT_TIF, post_only=DEFAULT_POST_ONLY, validate=bool(args.validate_only),
            cl_id=f"e2eSIM:{pair}:ENTRY:{int(time.time())}"
        )
        plan["entry"]["payload"] = entry_payload

        # TP SELL legs
        for leg in legs:
            p = build_add_order_payload(
                pair=pair, side="sell", ordertype="limit", price=leg["price"], volume=leg["qty"],
                tif=DEFAULT_TIF, post_only=DEFAULT_POST_ONLY, validate=bool(args.validate_only),
                cl_id=f"e2eSIM:{pair}:TP{leg['idx']}:{int(time.time())}"
            )
            leg["payload"] = p
            plan["tp_legs"].append(leg)

        # SL separate order (stop-loss or stop-loss-limit -> we model as stop-loss with trigger price)
        sl_trigger = round_price(entry_price * (1.0 + sl_pct / 100.0), price_dec)
        sl_payload = build_add_order_payload(
            pair=pair, side="sell", ordertype=JANITOR_CLOSE_ORDER_TYPE, price=sl_trigger, volume=total_qty,
            tif=JANITOR_CLOSE_TIF, post_only=0, validate=bool(args.validate_only),
            cl_id=f"e2eSIM:{pair}:SL:{int(time.time())}"
        )
        plan["sl"] = {"sl_pct": sl_pct, "trigger": sl_trigger, "payload": sl_payload}

        # Hypothetical breakeven amend after TP1
        if args.breakeven and plan["tp_legs"]:
            be_price = round_price(entry_price * (1.0 + (BE_OFFSET or 0.0) / 100.0), price_dec)
            plan["breakeven"]["hypothetical_amend_payload"] = {
                "action": "amend_sl_to_breakeven",
                "new_trigger_price": be_price,
                "note": "Hypothetical amend after TP1 fill"
            }

        plan["status"] = "ok"
        write_json(out_dir / f"{pair.replace('/', '_')}.plan.json", plan)

        # Summary line
        append_ndjson(summary_path, {
            "pair": pair, "guards_passed": True,
            "entry_price": entry_price, "qty": total_qty,
            "tp_prices": [l["price"] for l in plan["tp_legs"]],
            "tp_allocs": [l["alloc_pct"] for l in plan["tp_legs"]],
            "sl_trigger": plan["sl"]["trigger"],
            "legs_kept": len(plan["tp_legs"])
        })
        metrics_ok += 1
        report["ok_count"] += 1

    write_json(out_dir / "run_report.json", report)

    # Write metrics textfile
    metrics = [
        f'momentum_e2e_sim_pairs_total {report["pairs_total"]}',
        f'momentum_e2e_sim_runs_total{{status="ok"}} {metrics_ok}',
        f'momentum_e2e_sim_runs_total{{status="rejected"}} {metrics_rej}',
        f'momentum_e2e_sim_last_run_unixtime {int(time.time())}',
    ]
    metrics_path.write_text("\n".join(metrics) + "\n", encoding="utf-8")

    print(f"[e2e-sim] Completed: pairs_total={report['pairs_total']} ok={metrics_ok} rejected={metrics_rej}")
    print(f"[e2e-sim] Output dir: {out_dir}")

if __name__ == "__main__":
    main()

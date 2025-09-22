import os, sys, time, json, subprocess, argparse
from typing import Optional, List, Dict, Any
from momentum.ranker.selector import rank_and_select

def pick_pair(app_path: str, top_k: int) -> Optional[str]:
    sel = rank_and_select(app_path=app_path, top_k=top_k or 1)
    if not sel:
        return None
    return sel[0].get("pair")

def run_probe(pair: str, qty: float, limit_price: float) -> Dict[str, Any]:
    # Use the same Python interpreter (venv) and module to build payload
    cmd = [
        sys.executable, "-m", "momentum.scripts.ws_payload_probe",
        "--symbol", pair, "--side", "buy",
        "--qty", str(qty),
        "--limit", str(limit_price),
        "--tif", "gtc",
        "--validate", "1",
    ]
    out = subprocess.check_output(cmd, text=True)
    try:
        data = json.loads(out)
    except Exception:
        data = {"raw": out}
    return {"cmd": " ".join(cmd), "result": data}

def main():
    ap = argparse.ArgumentParser(description="Funnel runner (dry-run): select pair and preview WS add_order payload")
    ap.add_argument("--iterations", type=int, default=1, help="Number of cycles (default: 1)")
    ap.add_argument("--interval", type=float, default=5.0, help="Seconds between cycles (default: 5)")
    ap.add_argument("--qty", type=float, default=0.0001, help="Order quantity (base)")
    ap.add_argument("--limit", type=float, default=29000.0, help="Limit price (quote)")
    ap.add_argument("--top", type=int, default=1, help="Top-K selection (default: 1)")
    args = ap.parse_args()

    app = os.environ.get("APP")
    if not app:
        print("ERROR: APP env missing", file=sys.stderr)
        sys.exit(2)

    for i in range(max(1, args.iterations)):
        pair = pick_pair(app, args.top)
        if not pair:
            print(json.dumps({"cycle": i, "error": "no_pair_selected"}))
        else:
            notional = args.qty * args.limit
            preview = run_probe(pair, args.qty, args.limit)
            print(json.dumps({
                "cycle": i,
                "pair": pair,
                "qty": args.qty,
                "limit": args.limit,
                "notional_preview": notional,
                "ws_payload_probe": preview["result"]
            }, indent=2))
        sys.stdout.flush()
        if i + 1 < args.iterations:
            time.sleep(max(0.0, args.interval))

if __name__ == "__main__":
    main()

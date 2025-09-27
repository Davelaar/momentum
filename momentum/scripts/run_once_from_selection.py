#!/usr/bin/env python3
import os, json, argparse, subprocess, sys, csv, shlex

APP = os.environ.get("APP",".")

def iter_selection_rows(selection_csv):
    with open(selection_csv, newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
    # voorkeur voor BREAKOUT
    breakout = [row for row in rows if (row.get("tactic","") or "").upper()=="BREAKOUT"]
    return breakout + [row for row in rows if row not in breakout]

def try_validate(symbol: str) -> tuple[bool,str]:
    """
    Probeert een mini validate-order om permissions te checken.
    Return (ok, raw_json_string).
    """
    py = os.path.join(APP, ".venv", "bin", "python")
    # we gebruiken bracketd in validate-modus met heel lage notional: limit 10 (maakt niet uit, validate=1)
    env = os.environ.copy()
    env["ENTRY_MAX_NOTIONAL"] = "10"
    cmd = [
        py, "-u", "-m", "momentum.scripts.bracketd",
        "--symbol", symbol,
        "--limit", "10",
        "--use-ask", "1",
        "--validate", "1",
        "--reconcile", "0",
    ]
    try:
        out = subprocess.check_output(cmd, env=env, text=True, stderr=subprocess.STDOUT, timeout=25)
        # check op bekende fout
        if "Invalid permissions" in out:
            return False, out
        return True, out
    except subprocess.CalledProcessError as e:
        return False, e.output
    except Exception as e:
        return False, str(e)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection", default=os.path.join(APP,"var","funnel","selection.csv"))
    ap.add_argument("--validate", type=int, default=0)
    ap.add_argument("--use-ask", dest="use_ask", type=int, default=1)
    ap.add_argument("--limit", type=float, default=9999)
    args = ap.parse_args()

    chosen = None
    probe_log = []
    for row in iter_selection_rows(args.selection):
        sym = row["symbol"].strip()
        ok, log = try_validate(sym)
        probe_log.append({"symbol": sym, "ok": ok})
        if ok:
            chosen = sym
            break

    if not chosen:
        print(json.dumps({"error":"no tradable symbol found (permissions)","probes":probe_log}, indent=2))
        sys.exit(2)

    py = os.path.join(APP, ".venv", "bin", "python")
    cmd = [
        py, "-u", "-m", "momentum.scripts.bracketd",
        "--symbol", chosen,
        "--limit", str(args.limit),
        "--use-ask", str(args.use_ask),
        "--validate", str(args.validate),
        "--reconcile", "1",
    ]
    print(json.dumps({"picked": chosen, "probes": probe_log, "run": cmd}, indent=2))
    sys.exit(subprocess.call(cmd))

if __name__ == "__main__":
    main()

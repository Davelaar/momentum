#!/usr/bin/env python3
import os, sys, csv, json, time, shutil, argparse, subprocess, math
from pathlib import Path
from datetime import datetime, timezone
from momentum.funnel.exclude_hook import get_exclude_pattern

def find_app() -> Path:
    app = os.environ.get("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum"
    return Path(app).resolve()

def run_cmd(cmd, env=None, cwd=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, cwd=cwd)
    out_lines = []
    for line in p.stdout:
        out_lines.append(line.rstrip())
        print(line, end="")
    p.wait()
    return p.returncode, "\n".join(out_lines)

def detect_selection_csv(app: Path):
    candidates = [app / "var" / "funnel" / "selection.csv", app / "var" / "selection.csv", app / "selection.csv"]
    for c in candidates:
        if c.exists() and c.is_file() and c.stat().st_size > 0:
            return c
    for p in (app / "var").glob("**/selection*.csv"):
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None

def clamp_qty_limit(qty: float, limit: float, entry_max: float):
    if entry_max <= 0:
        return qty, limit
    notion = qty * limit
    if notion <= entry_max:
        return qty, limit
    if qty >= 1:
        new_qty = max(1, math.floor(entry_max / max(0.01, limit)))
        return float(new_qty), limit
    else:
        new_qty = entry_max / max(0.01, limit)
        return new_qty, limit

def main(argv=None):
    argv = argv or sys.argv[1:]
    DEFAULT_TOP = int(os.environ.get("FUNNEL_TOP", "50") or "50")
    DEFAULT_QTY = float(os.environ.get("FUNNEL_QTY", "1") or "1")
    DEFAULT_LIMIT = float(os.environ.get("FUNNEL_LIMIT", "10") or "10")

    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--qty", type=float, default=DEFAULT_QTY)
    ap.add_argument("--limit", type=float, default=DEFAULT_LIMIT)
    ap.add_argument("--apply-excludes", action="store_true")
    args = ap.parse_args(argv)

    app = find_app()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = app / "var" / "e2e_runs" / "funnel_rightside_testB" / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("APP", str(app))
    env.setdefault("PYTHONPATH", str(app))

    entry_max = float(env.get("ENTRY_MAX_NOTIONAL", "10"))
    qty, limit = clamp_qty_limit(args.qty, args.limit, entry_max)

    uni = app / "var" / "universe.json"
    if (not uni.exists()) or (uni.stat().st_size == 0):
        run_cmd([str(app / ".venv" / "bin" / "python"), "-m", "momentum.scripts.build_universe", "--app", str(app)], env=env, cwd=str(app))

    cmd = [str(app / ".venv" / "bin" / "python"), "-m", "momentum.scripts.funnel_runner_dryrun",
           "--iterations", "1", "--interval", "0", "--qty", str(qty), "--limit", str(limit), "--top", str(args.top)]
    code, out = run_cmd(cmd, env=env, cwd=str(app))
    (run_dir / "runner.log").write_text(out, encoding="utf-8")

    sel = detect_selection_csv(app)
    if not sel:
        print("selection.csv not found")
        return 1

    if args.apply_excludes and get_exclude_pattern() is not None:
        out_sel = run_dir / "selection_excluded.csv"
        with open(sel, newline="", encoding="utf-8") as fi, open(out_sel, "w", newline="", encoding="utf-8") as fo:
            rdr = csv.reader(fi); w = csv.writer(fo)
            headers = next(rdr, None); 
            if headers: w.writerow(headers)
            lower = [h.strip().lower() for h in (headers or [])]
            sym_idx = next((i for i,h in enumerate(lower) if h in ("symbol","pair","wsname")), 0)
            import re
            pat = os.environ.get("FUNNEL_EXCLUDE_SYMBOLS","")
            rx = re.compile(pat) if pat else None
            for row in rdr:
                sym = row[sym_idx] if sym_idx < len(row) else ""
                if rx and rx.search(sym):
                    continue
                w.writerow(row)
        out_path = out_sel
    else:
        import shutil
        out_path = run_dir / "selection.csv"
        try:
            import shutil
            shutil.copy2(sel, out_path)
        except Exception:
            pass

    rightside = {k: env.get(k) for k in [
        "RIGHTSIDE_ALLOW_MEANREV","RIGHTSIDE_REQUIRE_EMA_UP","RIGHTSIDE_MIN_RET1M_PCT","RIGHTSIDE_MIN_P15_PCT"
    ]}
    summary = {
        "app": str(app),
        "run_dir": str(run_dir),
        "ts": ts,
        "rightside": rightside,
        "entry_max": entry_max,
        "effective_qty": qty,
        "effective_limit": limit,
        "applied_excludes": bool(args.apply_excludes),
        "selection_csv_path": str(sel),
        "output_selection": str(out_path),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

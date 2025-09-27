#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
e2e_funnel_rightside.py
End-to-end testbundle A–Z for Funnel + Right-Side gates.

- Uses the *existing* funnel pipeline (no code changes) and sets the RIGHTSIDE*
  envs in-process (hard-exported) for this test run.
- Produces a self-contained run folder under $APP/var/e2e_runs/funnel_rightside_testA/<ts>/
  with: logs, copied selection.csv, and a summary.json/txt.
- Safe to run multiple times.

Assumptions:
- $APP points to /var/www/vhosts/snapdiscounts.nl/momentum (or your app path)
- momentum.scripts.funnel_runner_dryrun exists and can run a single iteration
- selection.csv will be produced in one of the known locations

Usage:
  $ APP=/var/www/vhosts/snapdiscounts.nl/momentum \
    PYTHONPATH="$APP" \
    "$APP/.venv/bin/python" -m momentum.scripts.e2e_funnel_rightside \
      --top 50 --qty 15 --limit 250 --breakout-only
"""
import os, sys, csv, json, time, shutil, argparse, subprocess
from pathlib import Path
from datetime import datetime

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
    # Common locations to probe
    candidates = [
        app / "var" / "selection.csv",
        app / "selection.csv",
        app / "var" / "funnel" / "selection.csv",
    ]
    for c in candidates:
        if c.exists() and c.is_file() and c.stat().st_size > 0:
            return c
    # try listing var/ for any selection*.csv
    for p in (app / "var").glob("**/selection*.csv"):
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None

def parse_selection(path: Path, max_rows=200):
    rows = []
    headers = None
    with open(path, newline="", encoding="utf-8") as f:
        sniffer = csv.Sniffer()
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
        reader = csv.reader(f, dialect)
        for i, row in enumerate(reader):
            if i == 0:
                headers = [h.strip().lower() for h in row]
                continue
            if not row or all((c.strip()=="" for c in row)):
                continue
            mapped = {}
            for h, c in zip(headers, row):
                mapped[h] = c.strip()
            rows.append(mapped)
            if len(rows) >= max_rows:
                break
    return headers or [], rows

def to_float(x, default=None):
    try:
        # replace potential thousands separators or exotic spacing
        return float(str(x).replace(",", ".").strip())
    except Exception:
        return default

def main(argv=None):
    argv = argv or sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=50, help="Top-N in funnel runner (if supported)")
    ap.add_argument("--qty", type=int, default=10, help="Qty param passthrough to existing runner")
    ap.add_argument("--limit", type=int, default=200, help="Limit param passthrough to existing runner")
    ap.add_argument("--breakout-only", action="store_true", help="Force RIGHTSIDE_ALLOW_MEANREV=0")
    ap.add_argument("--min-ret1m", type=float, default=0.05, help="RIGHTSIDE_MIN_RET1M_PCT threshold")
    ap.add_argument("--min-p15", type=float, default=0.10, help="RIGHTSIDE_MIN_P15_PCT threshold")
    ap.add_argument("--require-ema-up", action="store_true", help="Set RIGHTSIDE_REQUIRE_EMA_UP=1")
    args = ap.parse_args(argv)

    app = find_app()
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_dir = app / "var" / "e2e_runs" / "funnel_rightside_testA" / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "runner.log"

    # Prepare env (hard-exported RIGHTSIDE* gates)
    env = os.environ.copy()
    env.setdefault("APP", str(app))
    env.setdefault("PYTHONPATH", str(app))
    env["RIGHTSIDE_ALLOW_MEANREV"] = "0" if args.breakout_only else env.get("RIGHTSIDE_ALLOW_MEANREV", "1")
    env["RIGHTSIDE_MAX_MEANREV"] = env.get("RIGHTSIDE_MAX_MEANREV", "5")
    env["RIGHTSIDE_REQUIRE_EMA_UP"] = "1" if args.require_ema_up else env.get("RIGHTSIDE_REQUIRE_EMA_UP", "1")
    env["RIGHTSIDE_MIN_RET1M_PCT"] = str(args.min_ret1m)
    env["RIGHTSIDE_MIN_P15_PCT"] = str(args.min_p15)
    # Optional: allow exclusion via env if already configured; do not override here

    # 1) Universe check (build if missing / empty)
    uni = app / "var" / "universe.json"
    need_universe = (not uni.exists()) or (uni.stat().st_size == 0)
    out_lines = []
    out_lines.append(f"[info] APP={app}")
    out_lines.append(f"[info] run_dir={run_dir}")
    out_lines.append(f"[info] RIGHTSIDE envs: ALLOW_MEANREV={env['RIGHTSIDE_ALLOW_MEANREV']} REQUIRE_EMA_UP={env['RIGHTSIDE_REQUIRE_EMA_UP']} MIN_RET1M={env['RIGHTSIDE_MIN_RET1M_PCT']} MIN_P15={env['RIGHTSIDE_MIN_P15_PCT']}")

    if need_universe:
        out_lines.append("[step] universe.json missing/empty → building via momentum.scripts.build_universe")
        code, out = run_cmd([str(app / ".venv" / "bin" / "python"), "-m", "momentum.scripts.build_universe", "--app", str(app)], env=env, cwd=str(app))
        out_lines.append(out)
        if code != 0:
            out_lines.append(f"[warn] build_universe exit {code}. Continuing anyway.")

    # 2) Run funnel pipeline once
    out_lines.append("[step] running funnel_runner_dryrun (single iteration)")
    cmd = [str(app / ".venv" / "bin" / "python"), "-m", "momentum.scripts.funnel_runner_dryrun",
           "--iterations", "1",
           "--interval", "0",
           "--qty", str(args.qty),
           "--limit", str(args.limit),
           "--top", str(args.top)]
    code, out = run_cmd(cmd, env=env, cwd=str(app))
    out_lines.append(out)
    if code != 0:
        out_lines.append(f"[error] funnel_runner_dryrun exit code {code}")

    # 3) Collect selection.csv
    sel = detect_selection_csv(app)
    summary = {
        "app": str(app),
        "run_dir": str(run_dir),
        "ts": ts,
        "rightside": {
            "allow_meanrev": env["RIGHTSIDE_ALLOW_MEANREV"],
            "require_ema_up": env["RIGHTSIDE_REQUIRE_EMA_UP"],
            "min_ret1m_pct": env["RIGHTSIDE_MIN_RET1M_PCT"],
            "min_p15_pct": env["RIGHTSIDE_MIN_P15_PCT"],
        },
        "selection_csv_found": bool(sel),
        "selection_csv_path": str(sel) if sel else None,
        "stats": {},
        "notes": []
    }
    if sel:
        # copy to run dir
        dst = run_dir / "selection.csv"
        try:
            shutil.copy2(sel, dst)
        except Exception as e:
            out_lines.append(f"[warn] failed to copy selection.csv → {e}")
        # parse and produce a few counters
        headers, rows = parse_selection(sel, max_rows=1000)
        # normalize keys that we expect if available
        tactic_key = next((k for k in headers if k.lower() in ("tactic","strategy")), None)
        p15_key = next((k for k in headers if "15" in k and "pct" in k), None)
        ema_key = next((k for k in headers if "ema8" in k), None)

        n = len(rows)
        n_breakout = sum(1 for r in rows if tactic_key and r.get(tactic_key, "").upper()=="BREAKOUT")
        n_skip = sum(1 for r in rows if tactic_key and r.get(tactic_key, "").upper()=="SKIP")
        n_neg_p15_skip = 0
        if p15_key and tactic_key:
            for r in rows:
                p15 = to_float(r.get(p15_key), None)
                if p15 is not None and p15 < 0 and r.get(tactic_key, "").upper()=="SKIP":
                    n_neg_p15_skip += 1
        summary["stats"] = {
            "rows": n,
            "breakout": n_breakout,
            "skip": n_skip,
            "neg_p15_skip": n_neg_p15_skip
        }
        # Write a brief human summary
        top_lines = []
        top_lines.append(f"Rows: {n} | BREAKOUT: {n_breakout} | SKIP: {n_skip} | neg_p15→SKIP: {n_neg_p15_skip}")
        # list a few samples from each
        def sample_where(pred, limit=5):
            out = []
            for r in rows:
                try:
                    if pred(r):
                        out.append(r)
                        if len(out)>=limit:
                            break
                except Exception:
                    continue
            return out
        br_samples = sample_where(lambda r: tactic_key and r.get(tactic_key,"").upper()=="BREAKOUT")
        sk_samples = sample_where(lambda r: tactic_key and r.get(tactic_key,"").upper()=="SKIP")
        # Save CSV snippets
        snippet_path = run_dir / "samples.txt"
        with open(snippet_path, "w", encoding="utf-8") as fh:
            fh.write("[BREAKOUT samples]\n")
            for r in br_samples:
                sym = r.get("symbol") or r.get("pair") or "?"
                p15 = r.get(p15_key) if p15_key else "?"
                fh.write(f"- {sym} p15={p15}\n")
            fh.write("\n[SKIP samples]\n")
            for r in sk_samples:
                sym = r.get("symbol") or r.get("pair") or "?"
                p15 = r.get(p15_key) if p15_key else "?"
                fh.write(f"- {sym} p15={p15}\n")
        # notes
        if n_neg_p15_skip == 0:
            summary["notes"].append("No neg 15m → SKIP observed; verify right-side gating or data.")
    else:
        summary["notes"].append("selection.csv not found after funnel run. Check runner paths or pipeline output location.")

    # persist artifacts
    with open(run_dir / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines))

    # brief console status
    print("\n=== E2E Funnel Right-Side Test A — Summary ===")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    sys.exit(main())

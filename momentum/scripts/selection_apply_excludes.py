#!/usr/bin/env python3
import os, csv, argparse
from pathlib import Path
from momentum.funnel.exclude_hook import is_excluded

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)

    inp = Path(args.input); out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not inp.exists() or inp.stat().st_size == 0:
        raise SystemExit(f"input missing/empty: {inp}")

    with inp.open(newline="", encoding="utf-8") as fi, out.open("w", newline="", encoding="utf-8") as fo:
        reader = csv.reader(fi); writer = csv.writer(fo)
        headers = next(reader, None)
        if headers is None:
            raise SystemExit("empty CSV")
        writer.writerow(headers)
        lower = [h.strip().lower() for h in headers]
        sym_idx = next((i for i,h in enumerate(lower) if h in ("symbol","pair","wsname")), 0)
        rows=kept=0
        for row in reader:
            rows += 1
            sym = row[sym_idx] if sym_idx < len(row) else ""
            if is_excluded(sym):
                continue
            writer.writerow(row); kept += 1
    print(f"filtered: input_rows={rows} kept={kept} output={out}")

if __name__ == "__main__":
    main()

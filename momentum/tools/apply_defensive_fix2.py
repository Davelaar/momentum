
#!/usr/bin/env python3
"""apply_defensive_fix2.py
Re-applies a safe `_safe_get_pair` helper to momentum/scripts/e2e_sim_dryrun.py
and ensures it's inserted AFTER any `from __future__ import ...` lines.
"""
import os, sys, re, io

HELPER_SNIPPET = (
    "\n\ndef _safe_get_pair(row):\n"
    "    if isinstance(row, str):\n"
    "        return row\n"
    "    if isinstance(row, dict):\n"
    "        return row.get('pair') or row.get('wsname') or row.get('symbol')\n"
    "    return None\n"
)

def insert_helper_after_future(s: str) -> str:
    lines = s.splitlines(True)
    last_future_idx = -1
    for i, ln in enumerate(lines):
        # strict match at start of line ignoring leading spaces
        if ln.lstrip().startswith("from __future__ import"):
            last_future_idx = i
    if last_future_idx >= 0:
        insert_pos = sum(len(x) for x in lines[:last_future_idx+1])
        return s[:insert_pos] + HELPER_SNIPPET + s[insert_pos:]
    else:
        # If no future imports, put helper at the top
        return HELPER_SNIPPET + s

def main():
    app = os.environ.get("APP") or "."
    target = os.path.join(app, "momentum", "scripts", "e2e_sim_dryrun.py")
    if not os.path.isfile(target):
        print(f"ERROR: file not found: {target}", file=sys.stderr)
        sys.exit(2)

    with io.open(target, "r", encoding="utf-8") as f:
        s = f.read()

    if "_safe_get_pair(" not in s:
        s = insert_helper_after_future(s)

    pattern_chain = r"row\.get\([\"']pair[\"']\)\s*or\s*row\.get\([\"']wsname[\"']\)\s*or\s*row\.get\([\"']symbol[\"']\)"
    s = re.sub(pattern_chain, "_safe_get_pair(row)", s)

    s = re.sub(r"\bpair\s*=\s*row\.get\([^\n]+?\)", "pair = _safe_get_pair(row)", s)

    with io.open(target, "w", encoding="utf-8") as f:
        f.write(s)

    print("OK: defensive fix (v2) applied to", target)

if __name__ == "__main__":
    main()


#!/usr/bin/env python3
import os, sys, re, io

def main():
    app = os.environ.get("APP") or "."
    target = os.path.join(app, "momentum", "scripts", "e2e_sim_dryrun.py")
    if not os.path.isfile(target):
        print(f"ERROR: file not found: {target}", file=sys.stderr)
        sys.exit(2)
    with io.open(target, "r", encoding="utf-8") as f:
        s = f.read()

    # Inject helper if missing
    helper = (
        "\n\ndef _safe_get_pair(row):\n"
        "    if isinstance(row, str):\n"
        "        return row\n"
        "    if isinstance(row, dict):\n"
        "        return row.get('pair') or row.get('wsname') or row.get('symbol')\n"
        "    return None\n"
    )
    if "_safe_get_pair(" not in s:
        # place helper after imports (first two newlines after 'import')
        m = re.search(r"(\n)(?=[^\\n]*import)", s)
        insert_pos = 0
        # find end of first import block
        for m in re.finditer(r"^(?:from\\s+\\S+\\s+import\\s+.*|import\\s+\\S+.*)\\n", s, flags=re.M):
            insert_pos = m.end()
        if insert_pos == 0:
            insert_pos = 0
        s = s[:insert_pos] + helper + s[insert_pos:]

    # Replace row.get(...) chain with safe call in a robust way
    pattern = r"row\\.get\\([\"']pair[\"']\\)\\s*or\\s*row\\.get\\([\"']wsname[\"']\\)\\s*or\\s*row\\.get\\([\"']symbol[\"']\\)"
    s_new, n = re.subn(pattern, "_safe_get_pair(row)", s)
    if n == 0 and "_safe_get_pair(row)" not in s:
        print("WARN: did not find the expected pattern to replace; file may have been already fixed.", file=sys.stderr)
    else:
        s = s_new

    # Also make the consuming code tolerant if it checks attributes directly
    # e.g. 'for row in rows:' then 'pair = row.get(...)' → replace that assignment
    s = re.sub(r"pair\\s*=\\s*row\\.get\\([^\\n]+\\)", "pair = _safe_get_pair(row)", s)

    with io.open(target, "w", encoding="utf-8") as f:
        f.write(s)

    print("OK: defensive fix applied to", target)

if __name__ == "__main__":
    main()


from __future__ import annotations
import os, json, argparse
from rich.console import Console
from rich.table import Table
from rich import box
from momentum.observability.status import snapshot, FRESH_THRESHOLD_SEC

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default=os.environ.get("APP", os.getcwd()), help="APP path (default: $APP or cwd)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON snapshot")
    args = parser.parse_args()

    snap = snapshot(args.app)
    if args.json:
        print(json.dumps(snap, indent=2))
        return

    c = Console()
    c.print(f"[bold]Momentum Observability Status[/bold] (app=[italic]{args.app}[/italic])")
    c.print(f"Fresh threshold: {FRESH_THRESHOLD_SEC}s")

    hb = snap["heartbeats"]
    t1 = Table(title="Heartbeats", box=box.SIMPLE_HEAVY)
    t1.add_column("Source")
    t1.add_column("Exists")
    t1.add_column("Fresh")
    t1.add_column("Age (s)")
    t1.add_column("Note")
    for src in ["public_ws_v2", "public_ws_v1", "private_ws"]:
        s = hb[src]
        age = f"{s['age_seconds']:.1f}" if isinstance(s['age_seconds'], (int, float)) else "-"
        fresh = s['fresh']
        fresh_txt = "[green]yes[/green]" if fresh else ("[yellow]-[/yellow]" if fresh is None else "[red]no[/red]")
        t1.add_row(src, str(s["exists"]), fresh_txt, age, s.get("note",""))
    c.print(t1)

    st = snap["states"]
    t2 = Table(title="State files", box=box.SIMPLE_HEAVY)
    t2.add_column("Name")
    t2.add_column("Exists")
    t2.add_column("OK")
    t2.add_column("Count")
    t2.add_column("Note")
    for name in ["open_orders", "positions", "own_trades"]:
        s = st[name]
        t2.add_row(name, str(s["exists"]), str(s["ok"]), str(s["count"]), s.get("note",""))
    c.print(t2)

    j = snap["janitor"]
    t3 = Table(title="Janitor log (last ~50 lines scan)", box=box.SIMPLE_HEAVY)
    t3.add_column("Path")
    t3.add_column("Exists")
    t3.add_column("Error lines")
    t3.add_column("Note")
    t3.add_row(j["path"], str(j["exists"]), str(j["error_lines"]), j.get("note",""))
    c.print(t3)

if __name__ == "__main__":
    main()

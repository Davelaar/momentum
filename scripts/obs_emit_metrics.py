
from __future__ import annotations
import os, argparse, time
from momentum.observability.status import snapshot

def write_prom(metrics_path: str, snap):
    lines = []
    def m(line): lines.append(line)

    # Heartbeats
    for src in ["public_ws_v2", "public_ws_v1", "private_ws"]:
        s = snap["heartbeats"][src]
        age = s["age_seconds"] if isinstance(s["age_seconds"], (int, float)) else float('nan')
        fresh = 1 if s["fresh"] else 0 if s["fresh"] is not None else 0
        m(f'momentum_heartbeat_fresh{{source="{src}"}} {fresh}')
        m(f'momentum_heartbeat_age_seconds{{source="{src}"}} {age}')

    # States
    st = snap["states"]
    m(f'momentum_open_orders_count {st["open_orders"]["count"]}')
    m(f'momentum_positions_count {st["positions"]["count"]}')
    m(f'momentum_own_trades_count {st["own_trades"]["count"]}')

    # Janitor
    j = snap["janitor"]
    m(f'momentum_janitor_error_lines_tail50 {j["error_lines"]}')

    # Timestamp
    m(f'momentum_snapshot_unixtime {int(snap["ts"])}')

    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    tmp = metrics_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, metrics_path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default=os.environ.get("APP", os.getcwd()), help="APP path (default: $APP or cwd)")
    parser.add_argument("--out", default="var/metrics.prom", help="Output file for Prometheus metrics")
    args = parser.parse_args()

    snap = snapshot(args.app)
    out_path = args.out if os.path.isabs(args.out) else os.path.join(args.app, args.out)
    write_prom(out_path, snap)
    print(f"Wrote metrics to {out_path}")

if __name__ == "__main__":
    main()

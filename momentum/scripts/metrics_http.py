
from __future__ import annotations
import os, asyncio
from aiohttp import web
from momentum.observability.status import snapshot
from momentum.scripts.obs_emit_metrics import write_prom as _write_prom

APP_PATH = os.environ.get("APP", os.getcwd())
METRICS_FILE = os.path.join(APP_PATH, "var", "metrics.prom")

async def healthz(request: web.Request) -> web.Response:
    return web.Response(text="ok\n", content_type="text/plain")

def render_prom_text(snap) -> str:
    # mirror obs_emit_metrics.write_prom, but in-memory
    lines = []
    def m(line): lines.append(line)
    for src in ["public_ws_v2", "public_ws_v1", "private_ws"]:
        s = snap["heartbeats"][src]
        age = s["age_seconds"] if isinstance(s["age_seconds"], (int, float)) else float('nan')
        fresh = 1 if s["fresh"] else 0 if s["fresh"] is not None else 0
        m(f'momentum_heartbeat_fresh{{source="{src}"}} {fresh}')
        m(f'momentum_heartbeat_age_seconds{{source="{src}"}} {age}')
    st = snap["states"]
    m(f'momentum_open_orders_count {st["open_orders"]["count"]}')
    m(f'momentum_positions_count {st["positions"]["count"]}')
    m(f'momentum_own_trades_count {st["own_trades"]["count"]}')
    j = snap["janitor"]
    m(f'momentum_janitor_error_lines_tail50 {j["error_lines"]}')
    m(f'momentum_snapshot_unixtime {int(snap["ts"])}')
    return "\n".join(lines) + "\n"

async def metrics(request: web.Request) -> web.Response:
    try:
        snap = snapshot(APP_PATH)
        text = render_prom_text(snap)
        # also persist to file atomically for sidecar scrapers if desired
        os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
        tmp = METRICS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, METRICS_FILE)
        return web.Response(text=text, content_type="text/plain; version=0.0.4")
    except Exception as e:
        return web.Response(status=500, text=f"metrics_error {type(e).__name__}: {e}\n", content_type="text/plain")

def main():
    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/metrics", metrics)

    host = os.environ.get("OBS_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("OBS_HTTP_PORT", "9201"))
    web.run_app(app, host=host, port=port, print=None)

if __name__ == "__main__":
    main()

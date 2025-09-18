
# Observability & Ops (Step 12)

## TL;DR
- Health snapshot:
  ```bash
  sudo -u snapdiscounts bash -lc 'cd $APP && . .venv/bin/activate && python -m momentum.scripts.obs_status'
  ```
- Emit Prometheus-style metrics file:
  ```bash
  sudo -u snapdiscounts bash -lc 'cd $APP && . .venv/bin/activate && python -m momentum.scripts.obs_emit_metrics --out var/metrics.prom'
  ```
- Install systemd timer (optional, as root):
  ```bash
  cp $APP/systemd/momentum-obs-metrics.service /etc/systemd/system/
  cp $APP/systemd/momentum-obs-metrics.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now momentum-obs-metrics.timer
  ```

## What it checks
`obs_status` inspects these files (if present), with freshness thresholds:
- `var/public_ws_v2_hb.txt` (fresh if < 15s)
- `var/public_ws_v1_hb.txt` (fresh if < 15s; used when v2 falls back)
- `var/private_ws_hb.txt`   (fresh if < 15s)
- `var/open_orders_state.json` (parses JSON; shows count)
- `var/positions.json` (parses JSON; shows count)
- `var/own_trades_state.json` (parses JSON; shows count)
- `var/janitor.log` (tails last 50 lines; flags 'error' case-insensitively)

All checks are best-effort (missing files => 'absent', not failure).

## Metrics
`obs_emit_metrics` writes Prometheus text format to `--out` (default `var/metrics.prom`):
- `momentum_heartbeat_fresh{source="public_ws_v2"}` {0|1}
- `momentum_heartbeat_age_seconds{source="public_ws_v2"}` float
- Similar for `public_ws_v1` and `private_ws`
- `momentum_open_orders_count`, `momentum_positions_count`, `momentum_own_trades_count`
- `momentum_janitor_errors_5m` (grep last 5 min from `var/janitor.log` if timestamps found; fallback: 0/NA)

## Notes
- Timezone is Europe/Amsterdam (inherited from system env).
- No network calls; purely filesystem-based snapshot.
- Safe to run without Kraken creds.

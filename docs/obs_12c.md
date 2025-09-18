
# Step 12c — /metrics HTTP + logrotate

## Run HTTP server (systemd)
```bash
cp $APP/systemd/momentum-metrics-http.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now momentum-metrics-http.service
```

## Endpoints
- `GET /healthz` → `ok`
- `GET /metrics` → emits fresh metrics by invoking the snapshotter and returns Prometheus text format
  - On error, returns HTTP 500 with a short message

## Logrotate
Copy the config file:
```bash
cp $APP/etc/logrotate.d/momentum /etc/logrotate.d/momentum
```
It rotates:
- `$APP/var/public_ws.out`
- `$APP/var/private_ws.out` (if you log there)
- `$APP/var/metrics_http.out`
- `$APP/var/obs_metrics.timer.out` (if any future timers log to .out)

Policy: daily, keep 7, compress, copytruncate, missingok, notifempty.

## Sanity checks
```bash
# 1) HTTP health & metrics
curl -sS http://127.0.0.1:9201/healthz
curl -sS http://127.0.0.1:9201/metrics | head -n 20

# 2) Status snapshot
sudo -u snapdiscounts bash -lc 'cd $APP && . .venv/bin/activate && python -m momentum.scripts.obs_status'

# 3) Log files present?
ls -l $APP/var/*.out 2>/dev/null || echo "no .out files yet"

# 4) Test logrotate (dry-run, then force)
logrotate -d /etc/logrotate.d/momentum
logrotate -f /etc/logrotate.d/momentum
```

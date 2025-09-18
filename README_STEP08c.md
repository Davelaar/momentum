
# Step 8c — Private WS (openOrders & ownTrades) + systemd

Features
- Auth via WS token: uses env `KRAKEN_WS_TOKEN`, or fetches from REST with `KRAKEN_KEY/SECRET`.
- Subscribes to **openOrders** and **ownTrades** (v2 first, fallback to v1 auth WS).
- Idempotent upserts, partial-fill tolerant.
- Debounced flush (≤ 1s) to:
  - `$APP/var/open_orders_state.json`
  - `$APP/var/own_trades_state.json`
- Heartbeat file: `$APP/var/private_ws_hb.txt` (updates every ~5s).

## Run (manual)
```bash
sudo -u snapdiscounts bash -lc 'cd /var/www/vhosts/snapdiscounts.nl/momentum && . .venv/bin/activate && python -m momentum.scripts.ws_private_runner --app $PWD'
```

## Systemd unit
- File: `systemd/momentum-ws-private.service`
- Install:
  ```bash
  cp systemd/momentum-ws-private.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now momentum-ws-private.service
  ```

Logs: `$APP/var/ws_private.out.log` and `$APP/var/ws_private.err.log`.

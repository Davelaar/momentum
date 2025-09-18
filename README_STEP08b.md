
# Step 8b — Public WS (v2 with v1 fallback)

- Batch subscribe (default 6 symbols per 1200ms).
- Concurrency: receives messages continuously and updates a heartbeat file.
- Exponential backoff with jitter, capped ~300s.
- Warm-start from `$APP/var/universe.json` and limit via `WS_SYMBOL_LIMIT`.

## Run
```bash
sudo -u snapdiscounts bash -lc 'cd /var/www/vhosts/snapdiscounts.nl/momentum && . .venv/bin/activate && WS_SYMBOL_LIMIT=12 python -m momentum.scripts.ws_public_subscribe --app $PWD'
```

## Env
- `WS_SYMBOL_LIMIT` (default 24)
- `WS_BATCH_SIZE` (default 6)
- `WS_BATCH_INTERVAL_MS` (default 1200)
- `WS_PUBLIC_CHANNEL` (default `ticker`)
- `KRAKEN_WS_V2_URL` (default `wss://ws.kraken.com/v2`)
- `KRAKEN_WS_V1_URL` (default `wss://ws.kraken.com/`)

Heartbeat is written to `$APP/var/public_ws_v{1,2}_hb.txt`.

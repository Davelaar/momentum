# WS equity cache (balances snapshot)

- Script: `momentum/scripts/update_equity_cache_ws.py`
- Uses Kraken WebSocket v2 private `balances` channel to get USD cash.
- Requires:
  - `KRAKEN_KEY`, `KRAKEN_SECRET` (API key with WebSocket permission)
  - `APP` env for default output path

## Usage
```
export APP=/var/www/vhosts/snapdiscounts.nl/momentum
export KRAKEN_KEY=...; export KRAKEN_SECRET=...
$APP/.venv/bin/python -m momentum.scripts.update_equity_cache_ws --out "$APP/var/account_equity_usd.json"
jq . "$APP/var/account_equity_usd.json"
```
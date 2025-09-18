
# Step 8a — Universe (REST)

Fetch Kraken AssetPairs via REST, filter by `wsname` ending in `/USD`, and write `$APP/var/universe.json` with:
```json
{ "pair": "...", "tickrate_hz": null, "depth_quote_band": null, "spread_pct": null }
```

## Usage
```bash
sudo -u snapdiscounts bash -lc 'cd /var/www/vhosts/snapdiscounts.nl/momentum && . .venv/bin/activate && python -m momentum.scripts.build_universe --app $PWD'
```

Output prints the path and count. File is written to `$APP/var/universe.json`.

## Notes
- Uses `aiohttp` (already in env). No extra deps.
- Respects `APP` env var. Override via `--app`.
- Endpoint can be overridden with `KRAKEN_ASSETPAIRS_URL` if needed.

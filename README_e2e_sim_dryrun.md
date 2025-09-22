# Momentum — E2E Simulatie (dry-run) — Top-N laagste spread

Dit pakket voegt een **dry-run end-to-end simulatie** toe die:
- via de funnel de **top N** paren selecteert (default 50) op **laagste percentuele spread**,
- per pair een **orderplan** bouwt (entry + multi-TP + SL + hypothetische breakeven-amend),
- **geen echte orders** plaatst: alle payloads hebben `validate=1`,
- resultaten wegschrijft per pair + een summary en run_report.

## Snelstart (na deploy)
```bash
# Als user snapdiscounts (APP=/var/www/vhosts/snapdiscounts.nl/momentum)
cd "$APP"
. .venv/bin/activate

# Voorbeeld run (top-50, spread-ranking, default TP-schema 0.9/1.4/2.1)
python -m momentum.scripts.e2e_sim_dryrun \
  --top 50 \
  --rank spread \
  --qty 0.010 \
  --limit 58400 \
  --tp "0.9:50,1.4:30,2.1:20" \
  --sl "-0.5" \
  --breakeven 1 \
  --validate_only 1 \
  --output-dir var/e2e_runs/$(date +%F)
```

### Belangrijke flags
- `--top N` : top-N paren op basis van ranking (default 50).
- `--rank spread` : sorteer op **mediaan spread% (60s)** oplopend (default).
- `--spread_window_s 60` : glijdend venster voor mediaan (default 60).
- `--min_top_size` / `--min_quote_band_usd` : optionele liquiditeitsfilters.
- `--qty` en `--limit` : totale entry-hoeveelheid en entry-limit.
- `--tp "pct:alloc,…"` : TP-schema, bijv. `0.9:50,1.4:30,2.1:20`.
- `--sl "-0.5"` : stop-loss als pct vanaf entry (negatief = onder entry).
- `--breakeven 1` + `--breakeven_offset_pct 0.05` : hypothetische amend na TP1.
- `--output-dir` : doelmap voor per-pair plannen + samenvattingen.

### Output
- `var/e2e_runs/<date>/<pair>.plan.json`
- `var/e2e_runs/<date>/summary.ndjson`
- `var/e2e_runs/<date>/run_report.json`

### Metrics (lightweight)
Schrijft counters naar `var/metrics.d/e2e_sim.prom` (Prometheus textformat).
Als jullie `/metrics` endpoint die map reeds inleest, verschijnen ze daar;
zo niet, is dit non-invasief.

## Systemd (optioneel)
Zie `systemd/momentum-e2e-dryrun.service` en `.timer`. Pas het `--output-dir`
pad en frequentie naar wens aan voordat je de units activeert.

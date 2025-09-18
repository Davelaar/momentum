# Momentum — Opdracht stap 6 (Orders Executor — dry-run)

Deze stap levert een **dry-run Orders Executor** die Kraken **WS v2 `add_order`** payloads **opbouwt** (niet verzendt),
conform de documentatie (geen deprecated velden). Focus: **entry-limit**, **aparte SL**, **meerdere TP-legs** als **losse orders**.

**Belangrijk (projectregels):**
- Spot-only; **geen** `reduce_only`, **absolute** limit-prijzen voor entry.
- Guards: `ENTRY_MAX_NOTIONAL=$10` en `ONE_POSITION_ONLY=1` worden afgedwongen.
- Output: `/var/www/vhosts/snapdiscounts.nl/momentum/var/ws_payloads.json` (runtime-state, in `.gitignore`).

## CLI-voorbeeld

```bash
source /var/www/vhosts/snapdiscounts.nl/momentum/.venv/bin/activate
python -m momentum.scripts.exec_order   --symbol BTC/USD --side buy --qty 0.001 --limit 25000   --sl 24850 --sl_limit 24840   --tp "25200@40%,25300@60%:25290"   --validate 1 --dry_run 1
```

Dit genereert:
- **entry**: limit buy @ 25,000 (post_only indien gevraagd)
- **stop_loss-limit** @ 24,850 → limit 24,840 (met `triggers` → `price_type: static`, `reference: last`)
- **TP1**: take-profit market 40% @ 25,200
- **TP2**: take-profit-limit 60% @ 25,300 (limit 25,290)

Alles wordt **alleen** naar JSON geschreven (geen verzending).


Opdracht 9.0 — REST Reconciliation (orders/posities)
---------------------------------------------------
- CLI: `python -m momentum.scripts.reconcile_state --app $APP --dry-run 1`
- Schrijft bij `--dry-run 0` idempotent naar:
  * $APP/var/open_orders_state.json  (schema: open_orders_state/v1)
  * $APP/var/positions.json          (schema: positions_state/v1)
- Atomic writer met lock + fsync (tmp→rename), zodat corruptie bij crash voorkomen wordt.
- Diff-output toont add/change/remove per bestand.

Benodigd:
- Env: KRAKEN_KEY / KRAKEN_SECRET in `.env` (zoals eerder ingericht).

Opmerkingen:
- "Positions" zijn voor spot afgeleid van non-zero balances + USD-mark via public Ticker (mid).
- Geen wijzigingen aan bestaande modules vereist; standalone service.

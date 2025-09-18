
Opdracht 9.0 + 9a — Env-autoload + Atomic Writer/Migrator
---------------------------------------------------------
✅ Wat is nieuw
- REST client laadt automatisch `.env` via python-dotenv → geen `set -a` hack meer nodig.
- Atomic writer uitgebreid en voorzien van mini-migrator helper.
- CLI's:
  * `python -m momentum.scripts.reconcile_state --dry-run 1`
  * `python -m momentum.scripts.migrate_state`  (zet _schema naar v1 indien ontbreekt/verouderd)
  * `python -m momentum.scripts.writer_corruption_probe` (loop; Ctrl-C test → JSON blijft valide)

Gebruik
- Dry-run reconcile: `python -m momentum.scripts.reconcile_state --app $APP --dry-run 1`
- Live write:       `python -m momentum.scripts.reconcile_state --app $APP --dry-run 0`
- Migratie:         `python -m momentum.scripts.migrate_state --app $APP`
- Corruptie test:   `python -m momentum.scripts.writer_corruption_probe --app $APP`

Opmerking
- Schema targets: open_orders_state/v1, positions_state/v1 (data-ongewijzigd, idempotent).

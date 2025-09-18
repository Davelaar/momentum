
Opdracht 11 — Janitor → Executor (live) + null-safety
----------------------------------------------------
Wat nieuw is:
- Null-safe JSON readers (dict/list) zodat `'str'.get` nooit meer voorkomt.
- Debounce (default 5s) en token-bucket rate-limit (2 req/s, burst 4).
- Alle acties via WS v2:
  - `cancel_order` (per `order_id` of `cl_ord_id`)
  - `add_order` market met `reduce_only` voor closes
  - `amend_order` (algemene velden incl. trigger/price/qty)

Bestanden:
- momentum/state/json_safety.py
- momentum/util/rate_limit.py
- momentum/janitor/service.py
- momentum/scripts/janitor_run_once.py

Voorbeeld `var/janitor_actions.json`:
{
  "cancel": [{"cl_ord_id": "oto-...-TP2"}],
  "close":  [{"pair": "BTC/USD", "side": "sell", "qty": 0.004}],
  "amend":  [{"cl_ord_id": "oto-...-SL", "trigger_price": 25005.0, "trigger_price_type": "static"}]
}

Run once:
  sudo -u snapdiscounts bash -lc 'cd $APP && . .venv/bin/activate && python -m momentum.scripts.janitor_run_once --app $APP'

Log:
  tail -f $APP/var/janitor.log

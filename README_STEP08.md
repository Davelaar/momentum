
# Step 8 — Janitor -> Orders Executor

This step wires the Janitor's planned actions into Kraken WS v2 order payloads.

## CLI
Activate venv and run:

```bash
python -m momentum.scripts.janitor_plan_and_build --app $APP --dry
```

### Env knobs
- `JANITOR_CLOSE_ORDER_TYPE`: `market` (default) or `limit`
- `JANITOR_CLOSE_TIF`: default `ioc`
- `JANITOR_CLOSE_LIMIT_PRICE`: required when using `limit` closes (absolute price, no relative offsets)
- `ORDER_USERREF_PREFIX`: optional tag to group janitor orders

Input state files (relative to `$APP/var/`):
- `positions.json` (map: symbol -> {qty, opened_at, usd})
- `open_orders.json` (list of {order_id, symbol, side, qty, ...})

Output: JSON with planned actions and WS v2 payloads (add_order/cancel_order arrays).

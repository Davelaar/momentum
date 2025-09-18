# Momentum — Step 3 (Kraken WS v2 payload builder & safety guards)

This step adds a **payload builder + validators** for Kraken **Websocket v2 `add_order`** and a small probe to preview payloads without sending them.

What’s included:
- `momentum/exchange/kraken/ws_v2_payloads.py` — payload builders for:
  - primary orders (`limit`, `market`),
  - triggered orders (`stop-loss`, `take-profit`, `*-limit` via `triggers`),
  - **OTO** secondary via `conditional` (for stop-loss-limit / take-profit-limit).
- `momentum/utils/env.py` — loads tunables from `.env_meanrev` (keeps `.env` secrets separate).
- `momentum/utils/safety.py` — guards: `ENTRY_MAX_NOTIONAL`, `ONE_POSITION_ONLY` (soft placeholder), `ABS_LIMIT_REQUIRED` for limit orders.
- `momentum/models/intent.py` — intent models used to assemble payloads in a bot-friendly way.
- `momentum/scripts/ws_payload_probe.py` — prints JSON messages ready to send to `wss://ws-auth.kraken.com/v2` (with `validate=True` by default).

Docs references
- Kraken WS v2 Add Order (request schema, triggers, conditional/OTO, examples). See docs in your browser: https://docs.kraken.com/api/docs/websocket-v2/add_order/
- Kraken REST Add Order (parity checks): https://docs.kraken.com/api/docs/rest-api/add-order

## Quick use (probe)

From `APP=/var/www/vhosts/snapdiscounts.nl/momentum`:

```bash
$ source .venv/bin/activate
$ python -m momentum.scripts.ws_payload_probe --symbol BTC/USD --side buy --qty 0.001 --limit 28440   --sl 28410 --sl_limit 28400 --tif gtc --post_only 1 --validate 1
```

This prints a primary **limit** order plus an **OTO** secondary `stop-loss-limit` as a single `add_order` message. Nothing is sent to Kraken.

You can also preview a *standalone* take-profit-limit (non-OTO) message:

```bash
$ python -m momentum.scripts.ws_payload_probe --symbol BTC/USD --side sell --qty 0.001   --tp 28600 --tp_limit 28590 --standalone_tp 1
```

## Env knobs (in `.env_meanrev`)

```
ENTRY_MAX_NOTIONAL=10
ONE_POSITION_ONLY=1
ABS_LIMIT_REQUIRED=1
ALLOW_LIVE=0
DEFAULT_TIF=gtc
DEFAULT_STP=cancel_newest
DEADLINE_MS=5000
```

- `ALLOW_LIVE=0` keeps `validate=true` so orders won’t execute.
- `ENTRY_MAX_NOTIONAL=10` immediate safety brake for primary orders.
- `ONE_POSITION_ONLY=1` placeholder guard; wire this to your open-position tracker later.
- `ABS_LIMIT_REQUIRED=1` demands explicit `limit_price` for limit/stop-loss-limit/take-profit-limit.

## Notes

- OCO TP/SL **simultaneously** is *not* supported in a single WS v2 message: `conditional` allows **one** secondary template. To have both TP **and** SL, place the second leg as a separate `add_order` after the fill event (outside the scope of this step).
- We enforce **Spot only** (`margin=false`) and **no reduce_only** here per project rules.
- All builders add a **deadline** (now + `DEADLINE_MS`, default 5000ms).


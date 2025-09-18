
Opdracht 10.0 — Executor live-pad
---------------------------------
- WS v2 `add_order` via `wss://ws-auth.kraken.com/ws-auth/v2`.
- `validate` toggle (1 = dry-run bij broker), `post_only` flag via `oflags`.
- Exponential backoff + jitter bij netwerk/429, `CircuitBreaker` opent na drempel en koelt af.
- JSON ACK wordt geprint; bij succes `status: ok`, bij fout `status: error` met laatste broker-payload.

CLI Voorbeelden:
  # Dry-run (validate=1), limit BUY:
  python -m momentum.scripts.exec_add_order --pair XBT/USD --side buy --ordertype limit --volume 0.001 --price 10000 --validate 1

  # Live (validate=0), met post-only, max 3 retries:
  python -m momentum.scripts.exec_add_order --pair XBT/USD --side buy --ordertype limit --volume 0.001 --price 10000 --validate 0 --post-only 1 --max-retries 3

Benodigd:
- `.env` met KRAKEN_KEY/SECRET (autogeload) voor WebSockets token (GetWebSocketsToken) of zet `KRAKEN_WS_TOKEN` direct.

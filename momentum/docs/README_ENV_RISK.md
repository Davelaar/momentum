
# Env-driven risk sizing

## Wat is nieuw
- Auto-load `.env` en `.env_meanrev` (zonder CLI overrides).
- Risk sizing leest `ENTRY_*` en `EQUITY_*` uit env-files.
- Wrappers printen `env_driven: true` zodat je ziet dat het werkt.

## .env / .env_meanrev voorbeeld
```
# .env  (secrets)
KRAKEN_KEY=...
KRAKEN_SECRET=...

# .env_meanrev (knobs)
ENTRY_RISK_PCT=0.98
ENTRY_MAX_NOTIONAL=100
ENTRY_MIN_NOTIONAL=0
EQUITY_SOURCE=file
EQUITY_FILE=$APP/var/account_equity_usd.json
```

## Gebruik
1) Equity file maken (WS of handmatig) → `$APP/var/account_equity_usd.json`
2) Run dryrun zonder --qty; wrapper leest env automatisch.

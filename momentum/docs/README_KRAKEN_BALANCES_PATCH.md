# Kraken REST balances() patch

This patch adds `balances()` to `momentum/kraken/rest_client.py`:
- `async def balances(self) -> dict:` calls private endpoint `Balance`.
- No other behavior changes.

After deploying, `momentum.scripts.update_equity_cache` will be able to fetch USD cash.

## Deploy
```
unzip /root/uploads/kraken_rest_balances_patch.zip -d /root/uploads/_kr_bal_fix
rsync -a /root/uploads/_kr_bal_fix/momentum/ /var/www/vhosts/snapdiscounts.nl/momentum/momentum/
chown -R snapdiscounts:psacln /var/www/vhosts/snapdiscounts.nl/momentum
```

## Test
```
APP=/var/www/vhosts/snapdiscounts.nl/momentum
ALLOW_BALANCE_REST=1 $APP/.venv/bin/python -m momentum.scripts.update_equity_cache --out "$APP/var/account_equity_usd.json"
jq . "$APP/var/account_equity_usd.json"
```
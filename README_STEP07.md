# Momentum — Opdracht stap 7 (Janitor service)

Automatische cleanup:
- Sluit posities na 3 uur.
- Cancel dangling SELL-orders als holdings te klein zijn.
- Log: `/var/www/vhosts/snapdiscounts.nl/momentum/var/janitor.log`; acties: `/var/www/vhosts/snapdiscounts.nl/momentum/var/janitor_actions.json`.

## Test (single run)
```bash
source /var/www/vhosts/snapdiscounts.nl/momentum/.venv/bin/activate
python -m momentum.scripts.janitor --dry-run 1 --loop 0
tail -n 50 /var/www/vhosts/snapdiscounts.nl/momentum/var/janitor.log
cat /var/www/vhosts/snapdiscounts.nl/momentum/var/janitor_actions.json | jq .
```

## Systemd
```bash
cp -f /var/www/vhosts/snapdiscounts.nl/momentum/systemd/momentum-janitor.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now momentum-janitor
systemctl status momentum-janitor --no-pager
```

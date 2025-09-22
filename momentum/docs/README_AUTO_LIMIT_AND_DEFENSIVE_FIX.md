
# Auto-limit + Defensive fix

This package contains:
- `momentum/utils/price_feed.py` — fetch mids via public REST Ticker.
- `momentum/scripts/e2e_sim_dryrun_risk.py` — env-driven risk wrapper with auto limit.
- `momentum/scripts/e2e_sim_live.py` — live wrapper (validate_only=0) with auto limit.
- `momentum/tools/apply_defensive_fix.py` — in-place patch to make `e2e_sim_dryrun.py` tolerant to string rows.

## Install
```
unzip auto_limit_with_defensive_fix.zip -d /root/uploads/_auto_limit_fix
rsync -a /root/uploads/_auto_limit_fix/momentum/ /var/www/vhosts/snapdiscounts.nl/momentum/momentum/
chown -R snapdiscounts:psacln /var/www/vhosts/snapdiscounts.nl/momentum
```

## Apply defensive fix
```
sudo -u snapdiscounts bash -lc '
export APP=/var/www/vhosts/snapdiscounts.nl/momentum
. $APP/.venv/bin/activate
python -m momentum.tools.apply_defensive_fix'
```

## .env_meanrev
```
ENTRY_LIMIT_SOURCE=auto
ENTRY_LIMIT_OFFSET_PCT=-0.001
```

Now you can run wrappers without --limit; they will pick mid*(1+offset). The defensive patch prevents `.get()` crashes on string records inside `e2e_sim_dryrun.py`.

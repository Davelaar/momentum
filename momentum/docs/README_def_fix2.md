
# Defensive fix v2 (safe placement)

Contains:
- `momentum/tools/apply_defensive_fix2.py`

Places the helper after all `from __future__ import ...` lines,
avoiding the SyntaxError you saw.

## Install
```
unzip /root/uploads/auto_limit_def_fix2.zip -d /root/uploads/_auto_limit_def_fix2
rsync -a /root/uploads/_auto_limit_def_fix2/momentum/ /var/www/vhosts/snapdiscounts.nl/momentum/momentum/
chown -R snapdiscounts:psacln /var/www/vhosts/snapdiscounts.nl/momentum
```

## Apply
```
sudo -u snapdiscounts bash -lc '
APP=/var/www/vhosts/snapdiscounts.nl/momentum
. $APP/.venv/bin/activate
python -m momentum.tools.apply_defensive_fix2'
```


# WS runners as systemd services

## Install (as root)
```bash
cp /var/www/vhosts/snapdiscounts.nl/momentum/systemd/momentum-ws-public.service /etc/systemd/system/
cp /var/www/vhosts/snapdiscounts.nl/momentum/systemd/momentum-ws-private.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now momentum-ws-public.service
systemctl enable --now momentum-ws-private.service
```

## Status & logs
```bash
systemctl status momentum-ws-public.service
journalctl -u momentum-ws-public.service -n 100 -f
systemctl status momentum-ws-private.service
journalctl -u momentum-ws-private.service -n 100 -f
```

## Notes
- Services run as user 'snapdiscounts' with group 'psacln'.
- RestartPolicy is aggressive (always with 2s delay).
- WorkingDirectory and APP are pinned to the canonical path.
- Logs go to journal; you can still tail $APP/var/public_ws.out if your runner writes there.

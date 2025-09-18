Momentum – Step 12c: /metrics HTTP + logrotate
------------------------------------------------
Adds a minimal HTTP server exposing /metrics (Prometheus) without extra deps (uses aiohttp already in env) and logrotate snippets for var/*.out.
Contents:
- momentum/scripts/metrics_http.py        (aiohttp server on 127.0.0.1:9201)
- systemd/momentum-metrics-http.service   (systemd unit to run server)
- etc/logrotate.d/momentum                (logrotate rules for APP/var/*.out)
- docs/obs_12c.md                         (usage & sanity checks)

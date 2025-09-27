#!/usr/bin/env python3
import os, json
keys = [
    "RIGHTSIDE_ALLOW_MEANREV",
    "RIGHTSIDE_MAX_MEANREV",
    "RIGHTSIDE_REQUIRE_EMA_UP",
    "RIGHTSIDE_MIN_RET1M_PCT",
    "RIGHTSIDE_MIN_P15_PCT",
    "FUNNEL_EXCLUDE_SYMBOLS",
]
print(json.dumps({k: os.environ.get(k) for k in keys}, indent=2))

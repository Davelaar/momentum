import os, re
from typing import Optional

def get_exclude_pattern() -> Optional[re.Pattern]:
    pat = os.environ.get("FUNNEL_EXCLUDE_SYMBOLS", "").strip()
    if not pat:
        return None
    try:
        return re.compile(pat)
    except Exception:
        return None

def is_excluded(symbol: str) -> bool:
    rx = get_exclude_pattern()
    if not rx:
        return False
    return bool(rx.search(symbol or ""))

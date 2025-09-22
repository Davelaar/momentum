import os, json
from typing import List, Dict, Any, Optional

# Funnel/selector aligned to existing universe.json (WS v2 pipeline).
# No scoring logic yet: default score=1.0 and reasons placeholder, preserving existing behavior.

def _load_universe(app_path: Optional[str]) -> List[str]:
    if not app_path:
        return []
    path = os.path.join(app_path, "var", "universe.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Support both shapes:
        #  A) {"universe":[{"pair": "BTC/USD"}, ...]}
        #  B) {"pairs": ["BTC/USD", ...]}
        if isinstance(data, dict):
            if "universe" in data and isinstance(data["universe"], list):
                return [u.get("pair") for u in data["universe"] if isinstance(u, dict) and u.get("pair")]
            if "pairs" in data and isinstance(data["pairs"], list):
                return [p for p in data["pairs"] if isinstance(p, str)]
        return []
    except Exception:
        return []

def rank_and_select(app_path: Optional[str], top_k: int = 6) -> List[Dict[str, Any]]:
    pairs = _load_universe(app_path)
    # Fallback to a minimal safe subset if universe is empty.
    if not pairs:
        pairs = ["BTC/USD", "ETH/USD", "SOL/USD"]
    # Keep deterministic order for reproducibility; trivial score for now.
    pairs = sorted(list(dict.fromkeys(pairs)))[:max(1, top_k)]
    return [
        {"pair": p, "score": 1.0, "reasons": ["placeholder score = 1.0"]}
        for p in pairs
    ]

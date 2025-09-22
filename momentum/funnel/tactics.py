from __future__ import annotations
from typing import List, Dict, Any

def assign_and_score(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        rsi = r.get("rsi_15m", None)
        ema_ok = bool(r.get("ema8_gt_ema21", False))
        d15 = abs(r.get("pct_change_15m", 0.0))
        d1h = abs(r.get("pct_change_1h", 0.0))
        spread = r.get("spread_pct", None)
        tactic = "SKIP"
        if rsi is not None and spread is not None:
            if ema_ok and 60 <= rsi <= 80:
                tactic = "BREAKOUT"
            elif (not ema_ok and 40 <= rsi <= 55) or (rsi and rsi < 60 and spread < 0.10):
                tactic = "MEANREV"
        score = d15 + 0.5*d1h
        if spread is not None:
            score -= 0.5*spread
        if r.get("spread_atr_ratio") is not None:
            score -= min(r["spread_atr_ratio"], 1.0)
        r2 = dict(r)
        r2["tactic"] = tactic
        r2["score"] = round(score, 4)
        out.append(r2)
    # sort by score desc, then spread asc, then vol desc, then symbol
    out.sort(key=lambda x: (x.get("score",0), -x.get("spread_pct",9999), x.get("vol24h_usd",0), x.get("symbol","")), reverse=True)
    return out

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

FIAT_SET = {'USD','EUR','GBP','JPY','CAD','AUD','CHF','NZD','SEK','NOK','DKK'}
STABLE_SET = {'USDT','USDC','DAI','TUSD','PAX','BUSD','USDP','FDUSD','GUSD'}

@dataclass
class Pair:
    symbol: str  # e.g., 'BTC/USD'
    base: str
    quote: str

def filter_fiat_and_stables(pairs: List[Pair]) -> List[Pair]:
    out = []
    for p in pairs:
        if p.quote != 'USD':
            continue
        if p.base in FIAT_SET or p.base in STABLE_SET:
            continue
        out.append(p)
    return out

def apply_liquidity_filters(rows: List[Dict[str, Any]], min_vol24h_usd: float) -> List[Dict[str, Any]]:
    r = []
    for row in rows:
        vol = float(row.get('vol24h_usd', 0.0) or 0.0)
        if vol >= min_vol24h_usd:
            r.append(row)
    return r

def apply_anomaly_filters(rows: List[Dict[str, Any]], wick_max: float = 0.15, rsi_rollover: bool = True) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        flags = []
        wick = float(row.get('wick_ratio', 0.0) or 0.0)
        if wick > wick_max:
            flags.append('wick_excess')
        if rsi_rollover:
            rsi = row.get('rsi', None)
            rsi_down_bars = row.get('rsi_down_bars', 0)
            if isinstance(rsi, (int,float)) and rsi > 80 and rsi_down_bars >= 2:
                flags.append('rsi_rollover')
        if not flags:
            out.append(row)
    return out

from __future__ import annotations
import math, asyncio, aiohttp, time
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

KRAKEN_REST = "https://api.kraken.com/0/public"

def pct_change(curr: float, prev: float) -> float:
    if prev == 0:
        return 0.0
    return (curr/prev - 1.0) * 100.0

def ema(series: List[float], span: int) -> List[float]:
    if not series:
        return []
    k = 2/(span+1)
    out = [series[0]]
    for x in series[1:]:
        out.append(out[-1] + k*(x - out[-1]))
    return out

def rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period+1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, period+1):
        ch = prices[-i] - prices[-i-1]
        if ch >= 0:
            gains.append(ch)
        else:
            losses.append(-ch)
    avg_gain = sum(gains)/period if gains else 0.0
    avg_loss = sum(losses)/period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period+1:
        return 0.0
    trs = []
    prev_close = closes[-(period+1)]
    for i in range(period):
        h = highs[-period+i]
        l = lows[-period+i]
        c_prev = prev_close if i == 0 else closes[-period+i-1]
        tr = max(h-l, abs(h-c_prev), abs(l-c_prev))
        trs.append(tr)
    return sum(trs)/period if trs else 0.0

async def kraken_ohlc(session: aiohttp.ClientSession, pair: str, interval: int) -> Dict[str, Any]:
    # interval in minutes (1,5,15,60,...)
    params = {"pair": pair.replace('/',''), "interval": interval}
    async with session.get(f"{KRAKEN_REST}/OHLC", params=params, timeout=15) as resp:
        data = await resp.json()
        return data

async def kraken_ticker(session: aiohttp.ClientSession, pair: str) -> Dict[str, Any]:
    params = {"pair": pair.replace('/','')}
    async with session.get(f"{KRAKEN_REST}/Ticker", params=params, timeout=10) as resp:
        return await resp.json()

async def kraken_orderbook(session: aiohttp.ClientSession, pair: str, count: int = 10) -> Dict[str, Any]:
    params = {"pair": pair.replace('/',''), "count": count}
    async with session.get(f"{KRAKEN_REST}/Depth", params=params, timeout=10) as resp:
        return await resp.json()

async def compute_short_term_vol(pairs: List[str], top_n: int = 100) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    async with aiohttp.ClientSession() as session:
        tasks = [kraken_ohlc(session, p, 15) for p in pairs] + [kraken_ohlc(session, p, 60) for p in pairs]
        res = await asyncio.gather(*tasks, return_exceptions=True)
    # split results: first len(pairs) are 15m, next are 60m
    n = len(pairs)
    res15 = res[:n]
    res60 = res[n:]
    for i,p in enumerate(pairs):
        r15 = res15[i] if isinstance(res15[i], dict) else {}
        r60 = res60[i] if isinstance(res60[i], dict) else {}
        def last_close(rr):
            for k,v in rr.get("result", {}).items():
                if isinstance(v, list) and v:
                    return float(v[-1][4])
            return None
        def close_n_ago(rr, nago: int):
            for k,v in rr.get("result", {}).items():
                if isinstance(v, list) and len(v)>nago:
                    return float(v[-(nago+1)][4])
            return None
        c_now_15 = last_close(r15); c_15_ago = close_n_ago(r15, 1)
        c_now_60 = last_close(r60); c_60_ago = close_n_ago(r60, 1)
        row = {"symbol": p}
        if c_now_15 and c_15_ago:
            row["pct_change_15m"] = (c_now_15/c_15_ago - 1.0)*100.0
        if c_now_60 and c_60_ago:
            row["pct_change_1h"] = (c_now_60/c_60_ago - 1.0)*100.0
        out.append(row)
    # rank by |Δ15m| + 0.5*|Δ1h|
    def score(r):
        return abs(r.get("pct_change_15m",0.0)) + 0.5*abs(r.get("pct_change_1h",0.0))
    out.sort(key=score, reverse=True)
    return out[:top_n]

async def enrich_liquidity(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        tasks = [kraken_ticker(session, r["symbol"]) for r in rows]
        res = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(rows):
        data = res[i] if isinstance(res[i], dict) else {}
        # Kraken ticker result is a dict; we extract 'v' 24h base volume and 'p' last price to compute USD notional
        vol = None; lastp = None
        for k,v in data.get("result", {}).items():
            if isinstance(v, dict):
                v24 = v.get("v",[None,None])[-1]
                p = v.get("c",[None,None])[0]
                vol = float(v24) if v24 else None
                lastp = float(p) if p else None
                break
        if vol is not None and lastp is not None:
            r["vol24h_usd"] = vol * lastp
    return rows

async def enrich_spread(rows: List[Dict[str, Any]], count: int = 10) -> List[Dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        tasks = [kraken_orderbook(session, r["symbol"], count=count) for r in rows]
        res = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(rows):
        data = res[i] if isinstance(res[i], dict) else {}
        bid0 = ask0 = None
        for k,v in data.get("result", {}).items():
            if isinstance(v, dict):
                bids = v.get("bids", []); asks = v.get("asks", [])
                if bids: bid0 = float(bids[0][0])
                if asks: ask0 = float(asks[0][0])
                break
        if bid0 and ask0:
            r["bid0"] = bid0; r["ask0"] = ask0
            r["spread_pct"] = (ask0 - bid0) / ask0 * 100.0
    return rows

def compute_momentum_signals(rows: List[Dict[str, Any]], closes_5m: Dict[str, List[float]]) -> List[Dict[str, Any]]:
    for r in rows:
        p = r["symbol"]
        series = closes_5m.get(p, [])
        if len(series) >= 30:
            ema_fast = ema(series, 8)
            ema_slow = ema(series, 21)
            r["ema8_gt_ema21"] = (ema_fast[-1] > ema_slow[-1])
            r["rsi_15m"] = rsi(series[-15:], 14)
    return rows

def compute_spread_atr_ratio(rows: List[Dict[str, Any]], highs: Dict[str, List[float]], lows: Dict[str, List[float]], closes: Dict[str, List[float]], atr_len: int = 14) -> List[Dict[str, Any]]:
    for r in rows:
        p = r["symbol"]
        a = atr(highs.get(p,[]), lows.get(p,[]), closes.get(p,[]), atr_len)
        r["atr"] = a
        sp = r.get("spread_pct", None)
        if a and sp is not None:
            r["spread_atr_ratio"] = (sp/ a) if a != 0 else None
    return rows

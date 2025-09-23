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

# === APPEND-ONLY BLOCK: indicators (RSI/EMA/ATR) + compute_momentum_signals =============================
# This block ADDS functions; it does NOT modify or remove existing ones.
# Safe to append at the end of momentum/funnel/metrics.py

try:
    import aiohttp  # ensure available in your venv
except Exception as _e:
    aiohttp = None  # we handle lack of aiohttp gracefully

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default

# --- TA helpers (lightweight) ---
def _ema(series: List[float], period: int) -> List[float]:
    if not series or period <= 0:
        return []
    k = 2.0 / (period + 1.0)
    out = []
    ema_prev = sum(series[:period]) / period if len(series) >= period else series[0]
    for i, v in enumerate(series):
        if i < period:
            if i == period - 1:
                ema_prev = sum(series[:period]) / period
                out.append(ema_prev)
            else:
                out.append(float('nan'))
        else:
            ema_prev = (v - ema_prev) * k + ema_prev
            out.append(ema_prev)
    return out

def _rsi(series: List[float], period: int = 14) -> List[float]:
    if len(series) < period + 1:
        return [float('nan')] * len(series)
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(series)):
        ch = series[i] - series[i-1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_gain = sum(gains[1:period+1]) / period
    avg_loss = sum(losses[1:period+1]) / period
    out = [float('nan')] * period
    rs = (avg_gain / avg_loss) if avg_loss > 1e-12 else float('inf')
    out.append(100.0 - (100.0 / (1.0 + rs)))
    for i in range(period+1, len(series)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = (avg_gain / avg_loss) if avg_loss > 1e-12 else float('inf')
        out.append(100.0 - (100.0 / (1.0 + rs)))
    return out

def _true_range(highs: List[float], lows: List[float], closes: List[float]) -> List[float]:
    tr = []
    prev_close = None
    for h, l, c in zip(highs, lows, closes):
        if prev_close is None:
            tr.append(h - l)
        else:
            tr.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
        prev_close = c
    return tr

def _atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    tr = _true_range(highs, lows, closes)
    if len(tr) < period:
        return [float('nan')] * len(tr)
    out = [float('nan')] * (period - 1)
    first = sum(tr[:period]) / period
    out.append(first)
    prev = first
    for i in range(period, len(tr)):
        prev = (prev * (period - 1) + tr[i]) / period
        out.append(prev)
    return out

# --- Kraken 5m OHLC fetch + rate limiting ---
async def _fetch_ohlc(session, symbol: str, interval: int = 5):
    params = {"pair": symbol.replace("/", ""), "interval": str(interval)}
    async with session.get("https://api.kraken.com/0/public/OHLC", params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        data = await resp.json()
        if data.get("error"):
            raise RuntimeError(f"Kraken error for {symbol}: {data['error']}")
        res = data.get("result") or {}
        pair_key = next((k for k in res.keys() if k != "last"), None)
        rows = res.get(pair_key, [])
        # [time, open, high, low, close, vwap, volume, count]
        h = [float(r[2]) for r in rows]
        l = [float(r[3]) for r in rows]
        c = [float(r[4]) for r in rows]
        return h, l, c

async def _rate_limited_gather(tasks, per_minute: int, concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    interval = 60.0 / max(per_minute, 1)
    results = []
    last_time = 0.0
    async def runner(coro):
        nonlocal last_time
        async with sem:
            now = asyncio.get_event_loop().time()
            delay = max(0.0, (last_time + interval) - now)
            if delay > 0:
                await asyncio.sleep(delay)
            last_time = asyncio.get_event_loop().time()
            return await coro
    for t in tasks:
        results.append(asyncio.create_task(runner(t)))
    return await asyncio.gather(*results)

async def _compute_for_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if aiohttp is None:
        return rows  # no-op if aiohttp is missing
    budget_per_min = _env_int("REST_BUDGET_PER_MIN", 20)
    concurrency     = _env_int("REST_CONCURRENCY", 4)
    interval_min    = _env_int("MOMENTUM_INTERVAL_MIN", 5)
    bars            = _env_int("MOMENTUM_BARS", 120)
    topk            = _env_int("MOMENTUM_TOPK_FOR_INDICATORS", 40)

    # kies topK op absolute 15m move
    candidates = sorted(rows, key=lambda r: abs(r.get("pct_change_15m") or 0.0), reverse=True)[:topk]

    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_ohlc(session, r["symbol"], interval=interval_min) for r in candidates]
        fetched = await _rate_limited_gather(tasks, per_minute=budget_per_min, concurrency=concurrency)

    # indicators berekenen + terugschrijven
    for r, tup in zip(candidates, fetched):
        h, l, c = tup
        if len(c) < 21:
            continue
        ema8  = _ema(c, 8)
        ema21 = _ema(c, 21)
        rsi14 = _rsi(c, 14)
        atr14 = _atr(h, l, c, 14)
        def last_ok(vs):
            for v in reversed(vs):
                if v == v and not math.isinf(v):
                    return float(v)
            return None
        r["rsi_15m"] = last_ok(rsi14)
        e8 = last_ok(ema8); e21 = last_ok(ema21)
        r["ema8_gt_ema21"] = (e8 is not None and e21 is not None and e8 > e21)
        r["atr"] = last_ok(atr14)

    return rows

def compute_momentum_signals(rows: List[Dict[str, Any]], closes_5m: Dict[str, List[float]] | None = None) -> List[Dict[str, Any]]:
    """Append-only version: enrich rows with RSI/EMA/ATR using Kraken OHLC.
    Respects REST_BUDGET_PER_MIN, REST_CONCURRENCY, MOMENTUM_TOPK_FOR_INDICATORS.
    If aiohttp is unavailable, returns rows unchanged.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_compute_for_rows(list(rows)))
# === END APPEND-ONLY BLOCK ===============================================================================

# === APPEND-ONLY: MEANREV_BOUNCE now-signals =====================================================
import math, os
try:
    import aiohttp  # type: ignore
except Exception:
    aiohttp = None

def _bd_env_int(name, default):
    try: return int(os.environ.get(name, default))
    except Exception: return default

def _bd_env_float(name, default):
    try: return float(os.environ.get(name, default))
    except Exception: return default

def _bd_safe_last2(vs):
    clean=[float(x) for x in vs if isinstance(x,(int,float)) and x==x and not math.isinf(x)]
    return (None,None) if len(clean)<2 else (clean[-2], clean[-1])

async def _bd_fetch_ohlc_1m(session, symbol: str, interval: int = 1):
    params={"pair":symbol.replace("/",""),"interval":str(interval)}
    async with session.get("https://api.kraken.com/0/public/OHLC", params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        data=await resp.json()
        if data.get("error"): raise RuntimeError(f"Kraken error for {symbol}: {data['error']}")
        res=data.get("result") or {}; key=next((k for k in res.keys() if k!="last"), None); rows=res.get(key, [])
        o=[float(r[1]) for r in rows]; h=[float(r[2]) for r in rows]; l=[float(r[3]) for r in rows]; c=[float(r[4]) for r in rows]
        return o,h,l,c

async def _bd_enrich_now_signals(rows):
    if aiohttp is None: return rows
    budget=_bd_env_int("REST_BUDGET_PER_MIN", 20)
    conc=_bd_env_int("REST_CONCURRENCY", 4)
    topk=_bd_env_int("MOMENTUM_TOPK_FOR_INDICATORS", 40)
    lookback=_bd_env_int("BOUNCE_LOOKBACK_1M", 10)
    cands=sorted(rows, key=lambda r: abs(r.get("pct_change_15m") or 0.0), reverse=True)[:topk]
    async with aiohttp.ClientSession() as session:
        fetched=await _rate_limited_gather([_bd_fetch_ohlc_1m(session,r["symbol"],1) for r in cands],
                                           per_minute=budget, concurrency=conc)
    for r,(o,h,l,c) in zip(cands,fetched):
        if len(c)<max(lookback, 21): continue
        ema8=_ema(c,8)
        last_e8 = ema8[-1] if ema8 else None
        prev_c,last_c=_bd_safe_last2(c)
        if prev_c and last_c:
            r["ret_1m_pct"]=(last_c/prev_c - 1.0)*100.0
        if last_e8 is not None and last_c is not None and prev_c is not None:
            r["ema8_1m"]=float(last_e8)
            r["ema8_1m_cross_up"] = (last_c > last_e8) and (prev_c <= (ema8[-2] if len(ema8)>=2 else last_e8))
        window=c[-lookback:]; peak=max(window)
        if peak>0 and last_c is not None:
            r["drawdown_10m_pct"]=(last_c/peak - 1.0)*100.0
        rsi14=_rsi(c,14); pr,lr=_bd_safe_last2(rsi14)
        if pr is not None and lr is not None:
            r["rsi_15m_slope"]=float(lr-pr)
    return rows

try:
    _orig_compute_momentum_signals = compute_momentum_signals  # type: ignore[name-defined]
except Exception:
    _orig_compute_momentum_signals = None

def compute_momentum_signals(rows, closes_5m=None):  # type: ignore[override]
    base = _orig_compute_momentum_signals(rows, closes_5m) if callable(_orig_compute_momentum_signals) else rows
    base = [r for r in base if isinstance(r, dict)]
    loop = __import__("asyncio").new_event_loop()
    try:
        __import__("asyncio").set_event_loop(loop)
        base = loop.run_until_complete(_bd_enrich_now_signals(base))
    finally:
        loop.close()
    return base
# ================================================================================================
# === APPEND-ONLY: RIGHT-SIDE-OF-CANDLE GATE =============================================
def _rs_envf(name: str, default: float) -> float:
    import os
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default

def _rs_envi(name: str, default: int) -> int:
    import os
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default

def is_right_side_of_candle(row: dict) -> tuple[bool, str]:
    """Return (ok, reason)."""
    r1m = float(row.get("ret_1m_pct") or 0.0)
    p15 = float(row.get("pct_change_15m") or 0.0)
    req_ema_up = _rs_envi("RIGHTSIDE_REQUIRE_EMA_UP", 1) == 1
    if req_ema_up and not bool(row.get("ema8_gt_ema21")):
        return (False, "ema8_not_above_ema21")
    min_r1m = _rs_envf("RIGHTSIDE_MIN_RET1M_PCT", 0.05)
    min_p15 = _rs_envf("RIGHTSIDE_MIN_P15_PCT", 0.10)
    if r1m >= min_r1m and p15 >= min_p15:
        return (True, "breakout_ok")
    allow_bounce = _rs_envi("RIGHTSIDE_ALLOW_MEANREV", 1) == 1
    if allow_bounce:
        min_r1m_b = _rs_envf("RIGHTSIDE_MEANREV_MIN_RET1M_PCT", 0.08)
        max_p15_neg = _rs_envf("RIGHTSIDE_MEANREV_MAX_P15_NEG", -0.60)
        req_ema1m = _rs_envi("RIGHTSIDE_REQUIRE_EMA1M_CROSS", 1) == 1
        req_rsi_slope = _rs_envi("RIGHTSIDE_REQUIRE_RSI_SLOPE_UP", 0) == 1
        ema1m_ok = (bool(row.get("ema8_1m_cross_up")) or not req_ema1m)
        rsi_ok = ((float(row.get("rsi_15m_slope") or 0.0) > 0) or not req_rsi_slope)
        if p15 <= max_p15_neg and r1m >= min_r1m_b and ema1m_ok and rsi_ok:
            return (True, "bounce_ok")
    if r1m < min_r1m:
        return (False, "ret1m_below_min")
    if p15 < min_p15:
        return (False, "p15_below_min")
    return (False, "generic_reject")
# ========================================================================================
# === APPEND-ONLY: RIGHT-SIDE-OF-CANDLE GATE =============================================
def _rs_envf(name: str, default: float) -> float:
    import os
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default

def _rs_envi(name: str, default: int) -> int:
    import os
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default

def is_right_side_of_candle(row: dict) -> tuple[bool, str]:
    """Return (ok, reason)."""
    r1m = float(row.get("ret_1m_pct") or 0.0)
    p15 = float(row.get("pct_change_15m") or 0.0)
    req_ema_up = _rs_envi("RIGHTSIDE_REQUIRE_EMA_UP", 1) == 1
    if req_ema_up and not bool(row.get("ema8_gt_ema21")):
        return (False, "ema8_not_above_ema21")
    min_r1m = _rs_envf("RIGHTSIDE_MIN_RET1M_PCT", 0.05)
    min_p15 = _rs_envf("RIGHTSIDE_MIN_P15_PCT", 0.10)
    if r1m >= min_r1m and p15 >= min_p15:
        return (True, "breakout_ok")
    allow_bounce = _rs_envi("RIGHTSIDE_ALLOW_MEANREV", 1) == 1
    if allow_bounce:
        min_r1m_b = _rs_envf("RIGHTSIDE_MEANREV_MIN_RET1M_PCT", 0.08)
        max_p15_neg = _rs_envf("RIGHTSIDE_MEANREV_MAX_P15_NEG", -0.60)
        req_ema1m = _rs_envi("RIGHTSIDE_REQUIRE_EMA1M_CROSS", 1) == 1
        req_rsi_slope = _rs_envi("RIGHTSIDE_REQUIRE_RSI_SLOPE_UP", 0) == 1
        ema1m_ok = (bool(row.get("ema8_1m_cross_up")) or not req_ema1m)
        rsi_ok = ((float(row.get("rsi_15m_slope") or 0.0) > 0) or not req_rsi_slope)
        if p15 <= max_p15_neg and r1m >= min_r1m_b and ema1m_ok and rsi_ok:
            return (True, "bounce_ok")
    if r1m < min_r1m:
        return (False, "ret1m_below_min")
    if p15 < min_p15:
        return (False, "p15_below_min")
    return (False, "generic_reject")
# ========================================================================================

import os, json, math
def _to_float(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default
def load_knobs_from_env():
    return {
        "ENTRY_RISK_PCT": _to_float(os.environ.get("ENTRY_RISK_PCT"), None),
        "ENTRY_MAX_NOTIONAL": _to_float(os.environ.get("ENTRY_MAX_NOTIONAL"), None),
        "ENTRY_MIN_NOTIONAL": _to_float(os.environ.get("ENTRY_MIN_NOTIONAL"), None),
        "EQUITY_SOURCE": os.environ.get("EQUITY_SOURCE", "file"),
        "EQUITY_FILE": os.environ.get("EQUITY_FILE", os.path.join(os.environ.get("APP","."), "var", "account_equity_usd.json")),
        "ALLOW_BALANCE_REST": os.environ.get("ALLOW_BALANCE_REST", "0") in ("1","true","yes","on","True"),
    }
def read_equity_usd(knobs):
    src = knobs.get("EQUITY_SOURCE","file")
    if src == "file":
        path = knobs.get("EQUITY_FILE")
        if not path or not os.path.isfile(path):
            raise RuntimeError(f"equity file missing: {path!r}. Generate it first (update_equity_cache).")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "equity_usd" in data:
            return float(data["equity_usd"])
        raise RuntimeError("equity file invalid: expected {'equity_usd': <number>}")
    elif src == "rest":
        if not knobs.get("ALLOW_BALANCE_REST"):
            raise RuntimeError("REST equity disabled. Set ALLOW_BALANCE_REST=1 to enable.")
        import asyncio
        from momentum.services import reconciliation  # type: ignore
        async def _fetch():
            bals = await reconciliation.kraken.balances()
            usd = 0.0
            for k in ("ZUSD","USD"):
                if k in bals:
                    try:
                        usd += float(bals[k])
                    except Exception:
                        pass
            return usd
        return asyncio.get_event_loop().run_until_complete(_fetch())
    else:
        raise RuntimeError(f"Unknown EQUITY_SOURCE={src!r}")
def compute_notional(equity_usd, risk_pct, max_notional=None, min_notional=None):
    if risk_pct is None:
        raise RuntimeError("ENTRY_RISK_PCT is not set")
    desired = float(equity_usd) * float(risk_pct)
    capped = desired
    caps = []
    if min_notional is not None and capped < float(min_notional):
        caps.append(f"min:{capped:.8f}->{float(min_notional):.8f}")
        capped = float(min_notional)
    if max_notional is not None and capped > float(max_notional):
        caps.append(f"max:{capped:.8f}->{float(max_notional):.8f}")
        capped = float(max_notional)
    return desired, capped, caps
def compute_qty(limit_price, equity_usd, risk_pct, max_notional=None, min_notional=None):
    if not limit_price or float(limit_price) <= 0:
        raise RuntimeError("Limit price must be > 0 for risk-based sizing")
    desired, capped, caps = compute_notional(equity_usd, risk_pct, max_notional, min_notional)
    qty = capped / float(limit_price)
    return {
        "equity_usd": float(equity_usd),
        "risk_pct": float(risk_pct),
        "desired_notional": float(desired),
        "capped_notional": float(capped),
        "final_qty": float(qty),
        "caps_applied": caps,
    }
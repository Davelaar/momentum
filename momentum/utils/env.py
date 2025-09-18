
from __future__ import annotations
import os
from pathlib import Path

def load_env_knobs(app_root: str | None = None) -> dict:
    """Load tunables from `.env_meanrev` in APP root. .env with secrets is not touched here.
    Returns a dict with sensible defaults if file is absent.
    """
    path = Path(app_root or os.environ.get("APP", ".")) / ".env_meanrev"
    knobs = {
        "ENTRY_MAX_NOTIONAL": float(os.environ.get("ENTRY_MAX_NOTIONAL", "10")),
        "ONE_POSITION_ONLY": int(os.environ.get("ONE_POSITION_ONLY", "1")),
        "ABS_LIMIT_REQUIRED": int(os.environ.get("ABS_LIMIT_REQUIRED", "1")),
        "ALLOW_LIVE": int(os.environ.get("ALLOW_LIVE", "0")),
        "DEFAULT_TIF": os.environ.get("DEFAULT_TIF", "gtc"),
        "DEFAULT_STP": os.environ.get("DEFAULT_STP", "cancel_newest"),
        "DEADLINE_MS": int(os.environ.get("DEADLINE_MS", "5000")),
    }
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k in ("ENTRY_MAX_NOTIONAL", "DEADLINE_MS"):
                        knobs[k] = float(v) if k == "ENTRY_MAX_NOTIONAL" else int(v)
                    elif k in ("ONE_POSITION_ONLY", "ABS_LIMIT_REQUIRED", "ALLOW_LIVE"):
                        knobs[k] = int(v)
                    elif k in ("DEFAULT_TIF", "DEFAULT_STP"):
                        knobs[k] = v.strip()
    except Exception:
        # silent fallback to defaults
        pass
    return knobs

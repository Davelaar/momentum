# sitecustomize.py
import os, sys
from pathlib import Path

def _load_dotenv_file(path: Path):
    try:
        from dotenv import dotenv_values
    except Exception:
        return {}
    try:
        if path.exists():
            return dotenv_values(str(path))
    except Exception:
        return {}
    return {}

def _apply_if_missing(key, value):
    if key not in os.environ and value is not None:
        os.environ[key] = str(value)

def bootstrap():
    app = Path(os.environ.get("APP") or ".").resolve()
    env_base = _load_dotenv_file(app / ".env")
    env_meanrev = _load_dotenv_file(app / ".env_meanrev")
    for k, v in {**env_base, **env_meanrev}.items():
        if v is None: 
            continue
        if k not in os.environ:
            os.environ[k] = str(v)

    _apply_if_missing("RIGHTSIDE_ALLOW_MEANREV", "1")
    _apply_if_missing("RIGHTSIDE_MAX_MEANREV", "5")
    _apply_if_missing("RIGHTSIDE_REQUIRE_EMA_UP", "1")
    _apply_if_missing("RIGHTSIDE_MIN_RET1M_PCT", "0.05")
    _apply_if_missing("RIGHTSIDE_MIN_P15_PCT", "0.10")

    if os.environ.get("RIGHTSIDE_DEBUG_BOOT", "").lower() in ("1","true","yes","on"):
        import json
        cfg = {k: os.environ.get(k) for k in [
            "RIGHTSIDE_ALLOW_MEANREV","RIGHTSIDE_MAX_MEANREV",
            "RIGHTSIDE_REQUIRE_EMA_UP","RIGHTSIDE_MIN_RET1M_PCT","RIGHTSIDE_MIN_P15_PCT",
            "FUNNEL_EXCLUDE_SYMBOLS"
        ]}
        sys.stderr.write("[sitecustomize] RIGHTSIDE config loaded: " + json.dumps(cfg) + "\n")

bootstrap()

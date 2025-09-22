
import os, re
from typing import Dict, Iterable, Tuple

def _parse_lines(lines: Iterable[str]) -> Dict[str,str]:
    env = {}
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        # simple KEY=VALUE (allow quotes)
        if "=" not in s: 
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('\"\'')
        env[k] = v
    return env

def load_env_files(app_path: str | None = None, files: Tuple[str,...] = (".env",".env_meanrev"), override: bool=False) -> Dict[str,str]:
    """Load key/values from APP/{files} into os.environ (unless present).
    Returns the merged map. 'override=False' means existing env vars win.
    """
    app = app_path or os.environ.get("APP", ".")
    merged: Dict[str,str] = {}
    for fn in files:
        path = os.path.join(app, fn) if not os.path.isabs(fn) else fn
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = _parse_lines(f)
            merged.update(data)
            for k, v in data.items():
                if override or k not in os.environ:
                    # Allow $APP expansion in values
                    os.environ[k] = os.path.expandvars(v.replace("$APP", app))
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return merged

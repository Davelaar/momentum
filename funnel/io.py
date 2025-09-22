from __future__ import annotations
import json, os, tempfile, shutil, pathlib

def ensure_dir(p: str) -> None:
    pathlib.Path(p).parent.mkdir(parents=True, exist_ok=True)

def atomic_write_json(path: str, obj) -> None:
    ensure_dir(path)
    d = pathlib.Path(path).parent
    with tempfile.NamedTemporaryFile('w', dir=d, delete=False) as tmp:
        json.dump(obj, tmp, indent=2, sort_keys=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, path)

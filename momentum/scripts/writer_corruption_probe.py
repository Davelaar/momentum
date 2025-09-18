
from __future__ import annotations
import argparse, os, time, signal, json
from ..state.atomic_json import AtomicJSONWriter, read_json

def main():
    ap = argparse.ArgumentParser(description="Atomic writer probe: loop writes; safe to Ctrl-C at any time")
    ap.add_argument("--app", default=os.getenv("APP") or "/var/www/vhosts/snapdiscounts.nl/momentum")
    ap.add_argument("--file", default="var/probe_atomic.json")
    args = ap.parse_args()

    path = os.path.join(args.app, args.file)
    i = 0
    print("Writing every 200ms; press Ctrl-C to interrupt. After restart, file should be valid JSON.")
    try:
        while True:
            payload = {"i": i, "t": time.time(), "payload": {"nested": i % 5}}
            AtomicJSONWriter(path, schema_version="probe/v1").write(payload)
            i += 1
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Interrupted by user. Last successfully flushed JSON remains valid.")

    # Show result
    print("Final read:", read_json(path))

if __name__ == "__main__":
    main()

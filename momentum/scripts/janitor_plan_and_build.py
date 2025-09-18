
import os, json, argparse, time
from momentum.services.janitor import Janitor
from momentum.orders.executor import OrdersExecutor

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=os.environ.get("APP", "."), help="APP path (default from $APP)")
    ap.add_argument("--now", type=int, default=None, help="override now() timestamp")
    ap.add_argument("--dry", action="store_true", help="print only plan and payloads (no send)")
    args = ap.parse_args()

    jan = Janitor(app_path=args.app)
    plan = jan.plan(now_ts=args.now)

    execu = OrdersExecutor()
    ws_payloads = execu.build_from_plan(plan)

    out = {
        "ts": int(time.time()),
        "plan": plan,
        "ws_payloads": ws_payloads,
        "dry_run": True,
    }
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()

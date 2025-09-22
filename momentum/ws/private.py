import asyncio, os, time
from typing import Optional

DEFAULT_INTERVAL = int(os.environ.get("PRIVATE_HB_INTERVAL_SEC", "5"))

class PrivateWSManager:
    """
    Minimal-yet-correct private WS manager shell.
    - Keeps the service alive with an async runner.
    - Periodically updates var/private_ws_hb.txt to reflect liveness.
    - Designed to be extended with real auth/streams later without API breakage.
    """
    def __init__(self, app_path: Optional[str], flush_interval: Optional[float] = None):
        self.app_path = app_path or os.environ.get("APP", ".")
        self.flush_interval = float(flush_interval if flush_interval is not None else DEFAULT_INTERVAL)
        self._hb_path = os.path.join(self.app_path, "var", "private_ws_hb.txt")
        self._tasks = set()
        self._stopping = asyncio.Event()

    async def _heartbeat_writer(self):
        """Write epoch seconds to private heartbeat file at a fixed cadence."""
        os.makedirs(os.path.dirname(self._hb_path), exist_ok=True)
        while not self._stopping.is_set():
            try:
                with open(self._hb_path, "w") as f:
                    f.write(str(int(time.time())))
            except Exception:
                # Do not crash the manager on fs glitches; metrics will show stale age if persistent.
                pass
            try:
                await asyncio.sleep(self.flush_interval)
            except asyncio.CancelledError:
                break

    async def run(self):
        """
        Start background tasks (currently heartbeat). Extend here with:
        - WS auth token retrieval
        - account streams subscribe
        - message receiver & persistence
        """
        try:
            t_hb = asyncio.create_task(self._heartbeat_writer(), name="private_hb_writer")
            self._tasks.add(t_hb)
            await asyncio.gather(*self._tasks)
        finally:
            self._stopping.set()
            for t in list(self._tasks):
                t.cancel()
            if self._tasks:
                await asyncio.gather(*self._tasks, return_exceptions=True)

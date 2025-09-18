from . import __package__ as pkg  # type: ignore
from pathlib import Path
from ..l2_services.config import load_secrets
from ..l2_services.logger_setup import setup_logging
import logging

def main():
    setup_logging()
    log = logging.getLogger("probe_env")
    app = Path(__file__).resolve().parents[2]
    secrets = load_secrets()
    log.info("APP=%s", app)
    log.info("Has .env: %s", (app / ".env").exists())
    log.info("KRAKEN_KEY set: %s", bool(secrets.KRAKEN_KEY))
    log.info("KRAKEN_SECRET set: %s", bool(secrets.KRAKEN_SECRET))

if __name__ == "__main__":
    main()

from pathlib import Path
from dotenv import dotenv_values
from pydantic import BaseModel

APP = Path(__file__).resolve().parents[1]

class Secrets(BaseModel):
    KRAKEN_KEY: str | None = None
    KRAKEN_SECRET: str | None = None

def load_secrets() -> Secrets:
    env = dotenv_values(APP / ".env")
    return Secrets(**env)

"""Project paths and secrets."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / "secrets.yaml"
DB_PATH = ROOT / "records.sqlite3"
USER_AGENT = "RecordCollection/0.1 +https://github.com/somebox"

OPENROUTER_MODEL = "~google/gemini-flash-latest"


class ConfigError(Exception):
    pass


def load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        raise ConfigError(
            f"{SECRETS_PATH} not found — copy secrets.example.yaml and fill in your keys"
        )
    secrets = yaml.safe_load(SECRETS_PATH.read_text())
    for key in ("discogs_pat", "openrouter_key"):
        if not secrets.get(key):
            raise ConfigError(f"missing '{key}' in {SECRETS_PATH}")
    return secrets

"""Project paths, secrets, and optional settings."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / "secrets.yaml"
SETTINGS_PATH = ROOT / "settings.yaml"
DB_PATH = ROOT / "records.sqlite3"
USER_AGENT = "RecordCollection/0.1 +https://github.com/somebox/record-collection"

OPENROUTER_MODEL = "~google/gemini-flash-latest"

DEFAULT_SETTINGS = {
    "printer_model": "QL-700",   # any Brother QL model name
    "label_output": "printer",   # "printer" (USB) or "pdf" (for other printers)
    "pdf_dir": "labels-pdf",     # where PDF output lands, relative to the project
}


class ConfigError(Exception):
    pass


def load_secrets() -> dict:
    """discogs_pat is required; openrouter_key is optional (AI features off without it)."""
    if not SECRETS_PATH.exists():
        raise ConfigError(
            f"{SECRETS_PATH} not found — copy secrets.example.yaml and fill in your keys"
        )
    secrets = yaml.safe_load(SECRETS_PATH.read_text()) or {}
    if not secrets.get("discogs_pat"):
        raise ConfigError(f"missing 'discogs_pat' in {SECRETS_PATH}")
    return secrets


def load_settings() -> dict:
    """settings.yaml overrides the defaults; the file is optional."""
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        settings.update(yaml.safe_load(SETTINGS_PATH.read_text()) or {})
    return settings

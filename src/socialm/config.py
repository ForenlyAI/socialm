"""Ortam değişkenlerinden ve .env dosyasından ayar okuma."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_API_VERSION = "v23.0"
DEFAULT_DB_PATH = "data/socialm.db"


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: str | Path = ".env") -> None:
    """Basit .env okuyucu: KEY=VALUE satırlarını, zaten tanımlı değilse ortama ekler."""
    path = Path(path)
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    access_token: str
    ig_user_id: str
    api_version: str = DEFAULT_API_VERSION
    db_path: Path = Path(DEFAULT_DB_PATH)

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "Settings":
        load_dotenv(env_file)
        token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
        user_id = os.environ.get("IG_USER_ID", "").strip()
        missing = [name for name, val in (("IG_ACCESS_TOKEN", token), ("IG_USER_ID", user_id)) if not val]
        if missing:
            raise ConfigError(
                f"Eksik ayar: {', '.join(missing)}. .env.example dosyasını .env olarak kopyalayıp doldurun."
            )
        return cls(
            access_token=token,
            ig_user_id=user_id,
            api_version=os.environ.get("IG_API_VERSION", DEFAULT_API_VERSION).strip() or DEFAULT_API_VERSION,
            db_path=Path(os.environ.get("SOCIALM_DB", DEFAULT_DB_PATH)),
        )

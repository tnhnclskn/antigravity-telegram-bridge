"""
Configuration module for Antigravity Telegram Bridge.
Loads environment variables and provides structured settings.
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Load .env file
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, str(default)).strip().lower()
    return val in ("true", "1", "t", "yes", "y")


def _get_list_ints(key: str, default: Optional[List[int]] = None) -> List[int]:
    val = os.getenv(key, "").strip()
    if not val:
        return default or []
    result = []
    for part in val.split(","):
        part = part.strip()
        if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
            result.append(int(part))
    return result


class Settings:
    # Project paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    ATTACHMENTS_DIR: Path = DATA_DIR / "attachments"
    DB_PATH: Path = DATA_DIR / "bridge.db"

    # Telegram Bot Settings
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    ALLOWED_USER_IDS: List[int] = _get_list_ints("ALLOWED_USER_IDS")
    ADMIN_USER_IDS: List[int] = _get_list_ints("ADMIN_USER_IDS")
    
    # Auto-allow first user as Admin if whitelist is completely empty
    AUTO_WHITELIST_FIRST_USER: bool = _get_bool("AUTO_WHITELIST_FIRST_USER", True)

    # Antigravity CLI Settings
    AGY_BIN_PATH: str = os.getenv(
        "AGY_BIN_PATH",
        shutil.which("agy") or "/root/.local/bin/agy"
    ).strip()
    DEFAULT_WORKSPACE: str = os.getenv("DEFAULT_WORKSPACE", "/root").strip()
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini-3.7-flash-high").strip()
    DEFAULT_EFFORT: str = os.getenv("DEFAULT_EFFORT", "high").strip()
    AUTO_APPROVE_PERMISSIONS: bool = _get_bool("AUTO_APPROVE_PERMISSIONS", True)

    # Streaming and UI
    STREAM_UPDATES: bool = _get_bool("STREAM_UPDATES", True)
    STREAM_EDIT_INTERVAL: float = float(os.getenv("STREAM_EDIT_INTERVAL", "1.5"))
    MAX_TELEGRAM_MESSAGE_LEN: int = 4000  # Safe boundary below 4096

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def ensure_directories(cls):
        """Ensure necessary data directories exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate(cls):
        """Validate critical configuration parameters."""
        cls.ensure_directories()
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set. Please provide a valid bot token in .env")
        if not os.path.isfile(cls.AGY_BIN_PATH) and not shutil.which(cls.AGY_BIN_PATH):
            raise FileNotFoundError(f"Antigravity CLI binary not found at: {cls.AGY_BIN_PATH}")


settings = Settings()

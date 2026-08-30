# src/core/config.py
"""Лимиты выборки, заголовок приложения и тона статусов."""

import os
from pathlib import Path

APP_TITLE = "RED Virt Analytics"
APP_LAYOUT = "wide"
_VERSION_FALLBACK = "dev"

DEFAULT_ROW_LIMIT = 50
MAX_ROW_LIMIT = 2000
ROW_STEP = 10


def statement_timeout_ms() -> int:
    """Потолок времени SQL (мс). Переопределяется STATEMENT_TIMEOUT_MS в .env."""
    return int(os.getenv("STATEMENT_TIMEOUT_MS", "30000"))


def app_version(version_path: Path | None = None) -> str:
    """Версия из файла VERSION в корне приложения, иначе dev."""
    path = version_path if version_path is not None else (
        Path(__file__).resolve().parent.parent.parent / "VERSION"
    )
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return _VERSION_FALLBACK
    return text or _VERSION_FALLBACK


STATEMENT_TIMEOUT_MS = statement_timeout_ms()

DATAFRAME_HEIGHT = 500
DATAFRAME_ROW_PX = 36
DATAFRAME_HEADER_PX = 40
DATAFRAME_HEIGHT_PAD = 16
FONT_SIZE_CSS = "0.85rem"

# Не использовать green/red в модулях.
STATUS_TONE_CSS = {
    "success": "color: #2ecc71; font-weight: bold;",
    "warning": "color: #e67e22; font-weight: bold;",
    "critical": "color: #e74c3c; font-weight: bold;",
    "neutral": "color: #95a5a6;",
}

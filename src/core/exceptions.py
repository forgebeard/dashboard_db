"""Ошибки слоя данных: загрузка SQL без привязки к Streamlit."""

from __future__ import annotations

from core.config import STATEMENT_TIMEOUT_MS


class DataLoadError(Exception):
    """Не удалось прочитать данные из дампа PostgreSQL."""


def is_statement_timeout(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = type(current).__name__
        if name == "QueryCanceled":
            return True
        lowered = str(current).lower()
        if "statement timeout" in lowered or "querycanceled" in lowered:
            return True
        current = current.__cause__ or current.__context__
    return False


def format_load_error(exc: BaseException) -> str:
    if is_statement_timeout(exc):
        seconds = STATEMENT_TIMEOUT_MS // 1000
        return (
            f"Запрос прерван по таймауту ({seconds} с). "
            "Сузьте выборку или упростите SQL."
        )
    message = str(exc)
    lowered = message.lower()
    if "read-only" in lowered or "read only" in lowered:
        return (
            "База в режиме только чтение: изменение данных запрещено. "
            f"Детали: {message}"
        )
    return message

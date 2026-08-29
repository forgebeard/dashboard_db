"""Ошибки слоя данных: загрузка SQL без привязки к Streamlit."""

from __future__ import annotations

from typing import Literal

from core.config import statement_timeout_ms

LoadErrorKind = Literal["timeout", "undefined_column", "undefined_table", "read_only", "other"]


class DataLoadError(Exception):
    """Не удалось прочитать данные из дампа PostgreSQL."""

    def __init__(self, message: str, *, kind: LoadErrorKind = "other") -> None:
        super().__init__(message)
        self.kind = kind


def _walk_exceptions(exc: BaseException):
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_statement_timeout(exc: BaseException) -> bool:
    for current in _walk_exceptions(exc):
        if isinstance(current, DataLoadError) and current.kind == "timeout":
            return True
        name = type(current).__name__
        if name == "QueryCanceled":
            return True
        lowered = str(current).lower()
        if (
            "statement timeout" in lowered
            or "querycanceled" in lowered
            or "таймауту" in lowered
        ):
            return True
    return False


def is_undefined_column(exc: BaseException) -> bool:
    for current in _walk_exceptions(exc):
        if isinstance(current, DataLoadError) and current.kind == "undefined_column":
            return True
        if type(current).__name__ == "UndefinedColumn":
            return True
        lowered = str(current).lower()
        if "undefined column" in lowered:
            return True
        if "column" in lowered and "does not exist" in lowered:
            return True
    return False


def is_undefined_table(exc: BaseException) -> bool:
    for current in _walk_exceptions(exc):
        if isinstance(current, DataLoadError) and current.kind == "undefined_table":
            return True
        if type(current).__name__ == "UndefinedTable":
            return True
        lowered = str(current).lower()
        if "undefined table" in lowered or "undefinedtable" in lowered:
            return True
        if "relation" in lowered and "does not exist" in lowered:
            if "column" in lowered:
                continue
            return True
    return False


def should_retry_narrow_sql(exc: BaseException) -> bool:
    """Узкий SELECT только при отсутствии колонки, не при timeout/сети."""
    if isinstance(exc, DataLoadError) and exc.kind != "other":
        return exc.kind == "undefined_column"
    if is_statement_timeout(exc):
        return False
    return is_undefined_column(exc)


def _kind_from_exc(exc: BaseException) -> LoadErrorKind:
    if is_statement_timeout(exc):
        return "timeout"
    if is_undefined_column(exc):
        return "undefined_column"
    if is_undefined_table(exc):
        return "undefined_table"
    lowered = str(exc).lower()
    if "read-only" in lowered or "read only" in lowered:
        return "read_only"
    return "other"


def wrap_load_error(exc: BaseException) -> DataLoadError:
    if isinstance(exc, DataLoadError):
        return exc
    return DataLoadError(format_load_error(exc), kind=_kind_from_exc(exc))


def format_load_error(exc: BaseException) -> str:
    if is_statement_timeout(exc):
        seconds = statement_timeout_ms() // 1000
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

"""Общее оформление текстовых инспекторов: рамки, ключ: значение, даты."""

from __future__ import annotations

from datetime import datetime
from typing import Any

BAR_DOUBLE = "═" * 78
BAR_SINGLE = "─" * 78


def _safe_date(dt: Any) -> datetime | None:
    if not dt:
        return None
    return dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt


def _fmt_date(dt: Any) -> str:
    if not dt:
        return "—"
    parsed = _safe_date(dt)
    if parsed is None:
        return "—"
    return parsed.strftime("%d.%m.%Y %H:%M")


def _fmt_ts(dt: Any) -> str:
    if not dt:
        return "—"
    parsed = _safe_date(dt)
    if parsed is None:
        return "—"
    return parsed.strftime("%d.%m.%Y %H:%M:%S")


def _kv_at(indent: str, label: str, value: Any, width: int = 16) -> str:
    text = "—" if value is None or value == "" else str(value)
    return f"{indent}{(label + ':'):<{width}}{text}"


def _kv(label: str, value: Any, width: int = 16) -> str:
    return _kv_at("  ", label, value, width)


def _yes_no(flag: Any) -> str:
    return "да" if flag in (True, 1, "1", "t", "true", "True") else "нет"

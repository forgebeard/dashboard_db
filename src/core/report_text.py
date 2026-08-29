"""Общее оформление текстовых инспекторов: рамки и строки ключ: значение."""

from __future__ import annotations

from typing import Any

BAR_DOUBLE = "═" * 78
BAR_SINGLE = "─" * 78


def _kv_at(indent: str, label: str, value: Any, width: int = 16) -> str:
    text = "—" if value is None or value == "" else str(value)
    return f"{indent}{(label + ':'):<{width}}{text}"


def _kv(label: str, value: Any, width: int = 16) -> str:
    return _kv_at("  ", label, value, width)


def _yes_no(flag: Any) -> str:
    return "да" if flag in (True, 1, "1", "t", "true", "True") else "нет"

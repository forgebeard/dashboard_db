# src/core/ui_utils.py
"""Общие элементы UI: статусы, заголовок страницы, фильтры."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pandas as pd
import streamlit as st

from core.config import (
    DATAFRAME_HEADER_PX,
    DATAFRAME_HEIGHT,
    DATAFRAME_HEIGHT_PAD,
    DATAFRAME_ROW_PX,
    STATUS_TONE_CSS,
)
from core.constants import StatusTone


def fix_uuid_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Конвертирует uuid.UUID в строки для Streamlit. Модифицирует df inplace."""
    if df.empty:
        return df

    for col in df.columns:
        if df[col].dtype != "object":
            continue
        has_uuid = any(isinstance(val, uuid.UUID) for val in df[col])
        if not has_uuid:
            continue
        df[col] = df[col].apply(lambda x: str(x) if isinstance(x, uuid.UUID) else x)

    return df


def style_status_column(
    df: pd.DataFrame,
    tone_fn: Callable[[Any], StatusTone | None],
    *,
    status_col: str = "Статус",
    code_col: str = "_status_code",
    extra: Sequence[
        tuple[str, str, Callable[[Any], StatusTone | None]]
    ] = (),
    missing_css: str | None = None,
):
    """Раскрашивает колонки по числовому коду, не по тексту ячейки."""
    if df.empty:
        return df

    specs: list[tuple[str, str, Callable[[Any], StatusTone | None], str]] = []
    default_css = (
        STATUS_TONE_CSS["neutral"] if missing_css is None else missing_css
    )
    if status_col in df.columns and code_col in df.columns:
        specs.append((status_col, code_col, tone_fn, default_css))
    for col, extra_code_col, extra_tone_fn in extra:
        if col in df.columns and extra_code_col in df.columns:
            specs.append((col, extra_code_col, extra_tone_fn, ""))
    if not specs:
        return df

    styled = None
    for col, coded, fn, fallback in specs:
        codes = df[coded]

        def _css(
            _series: pd.Series,
            _codes: pd.Series = codes,
            _fn: Callable[[Any], StatusTone | None] = fn,
            _fallback: str = fallback,
        ) -> list[str]:
            styles: list[str] = []
            for code in _codes.loc[_series.index]:
                tone = _fn(code)
                styles.append(STATUS_TONE_CSS.get(tone, _fallback) if tone else _fallback)
            return styles

        if styled is None:
            styled = df.style.apply(_css, subset=[col])
        else:
            styled = styled.apply(_css, subset=[col])
    return styled if styled is not None else df


def render_load_error(exc: BaseException, what: str) -> None:
    """Сообщение об ошибке загрузки данных (не путать с пустым результатом)."""
    st.error(f"Ошибка загрузки {what}: {exc}")


def render_page_header(
    title: str,
    db_name: str,
    details: Sequence[str] | None = None,
) -> None:
    """Заголовок раздела и контекст дампа."""
    st.subheader(title)
    parts = [f"`{db_name}`"]
    if details:
        parts.extend(str(item) for item in details if item)
    st.caption(" · ".join(parts))


def render_health_filter(
    options: Sequence[tuple[str, str]],
    *,
    key: str,
    default: str = "all",
    label: str = "Состояние",
) -> str:
    """Одиночный фильтр по состоянию. options: (id, подпись)."""
    ids = [item[0] for item in options]
    labels = {item[0]: item[1] for item in options}
    if key not in st.session_state or st.session_state[key] not in ids:
        st.session_state[key] = default if default in ids else ids[0]
    selected = st.segmented_control(
        label,
        options=ids,
        format_func=lambda option_id: labels[option_id],
        key=key,
        label_visibility="collapsed",
    )
    return selected or default


def filters_are_active(defaults: Mapping[str, Any]) -> bool:
    for key, default in defaults.items():
        current = st.session_state.get(key, default)
        if current is None:
            current = default
        if str(current).strip() != str(default).strip():
            return True
    return False


def render_clear_filters_button(defaults: Mapping[str, Any], *, key: str) -> None:
    """Сбрасывает ключи виджетов, если они отличаются от значений по умолчанию."""
    if not filters_are_active(defaults):
        return

    def _clear() -> None:
        for widget_key, default in defaults.items():
            st.session_state[widget_key] = default

    st.button("Сбросить фильтры", on_click=_clear, key=key)


def dataframe_height(n_rows: int = 0) -> int:
    """Высота таблицы по числу строк, не выше DATAFRAME_HEIGHT."""
    rows = max(int(n_rows), 0)
    fitted = DATAFRAME_HEADER_PX + rows * DATAFRAME_ROW_PX + DATAFRAME_HEIGHT_PAD
    return min(DATAFRAME_HEIGHT, max(DATAFRAME_HEADER_PX + DATAFRAME_HEIGHT_PAD, fitted))

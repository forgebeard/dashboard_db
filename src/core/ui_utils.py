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
    tone_fn: Callable[[Any], StatusTone],
    *,
    status_col: str = "Статус",
    code_col: str = "_status_code",
):
    """Раскрашивает колонку статуса по числовому коду, не по тексту ячейки."""
    if df.empty or status_col not in df.columns or code_col not in df.columns:
        return df

    codes = df[code_col]

    def _css(_series: pd.Series) -> list[str]:
        styles: list[str] = []
        for code in codes.loc[_series.index]:
            tone = tone_fn(code)
            styles.append(STATUS_TONE_CSS.get(tone, STATUS_TONE_CSS["neutral"]))
        return styles

    return df.style.apply(_css, subset=[status_col])


def render_page_header(
    title: str,
    db_name: str,
    details: Sequence[str] | None = None,
    *,
    download: Mapping[str, Any] | None = None,
) -> None:
    """Заголовок раздела, CSV справа и контекст дампа."""
    title_col, csv_col = st.columns([5, 1], vertical_alignment="center")
    with title_col:
        st.subheader(title)
    with csv_col:
        if download:
            st.download_button(
                download.get("label", "Скачать CSV"),
                data=download["data"],
                file_name=download["file_name"],
                mime=download.get("mime", "text/csv"),
                key=download["key"],
                width="stretch",
            )
    parts = [f"`{db_name}`", "READ ONLY"]
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

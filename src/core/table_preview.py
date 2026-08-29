"""Превью сырых таблиц дампа: лимит строк, whitelist имён, expander."""

from __future__ import annotations

import json
import re

import pandas as pd
import streamlit as st
from sqlalchemy import text

from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP
from core.db_utils import get_sqlalchemy_engine, read_sql_df
from core.exceptions import DataLoadError
from core.ui_utils import fix_uuid_columns

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def assert_safe_ident(name: str) -> str:
    """Разрешает только обычные SQL-идентификаторы (без схемы и кавычек)."""
    if not _IDENT.fullmatch(name):
        raise ValueError(f"Недопустимое имя таблицы или колонки: {name!r}")
    return name


def _quoted(name: str) -> str:
    return f'"{assert_safe_ident(name)}"'


def _stringify_json_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(
            lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x)
        )
    return df


def _mask_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = "***MASKED***"
    return df


def render_grouped_table_preview(
    active_db: str,
    groups: dict[str, dict[str, str]],
    *,
    title: str,
    limit_key: str,
    order_overrides: dict[str, str] | None = None,
    row_limit_overrides: dict[str, int] | None = None,
    mask_columns: dict[str, list[str]] | None = None,
    json_text_columns: dict[str, list[str]] | None = None,
) -> None:
    """
    Отрисовывает лимит строк и группы expander'ов с SELECT * ... LIMIT.

    groups: {имя группы: {имя_таблицы: описание}}. Пустое имя группы не печатается.
    limit_key: уникальный key для st.number_input (уже с суффиксом БД).
    """
    allowed = {table for tables in groups.values() for table in tables}
    for name in allowed:
        assert_safe_ident(name)

    title_col, limit_col = st.columns([4, 1.2], vertical_alignment="bottom")
    with title_col:
        st.subheader(title)
    with limit_col:
        row_limit = st.number_input(
            "Лимит строк",
            min_value=10,
            max_value=MAX_ROW_LIMIT,
            value=DEFAULT_ROW_LIMIT,
            step=ROW_STEP,
            key=limit_key,
        )
    row_limit = min(int(row_limit), MAX_ROW_LIMIT)

    order_overrides = order_overrides or {}
    row_limit_overrides = row_limit_overrides or {}
    mask_columns = mask_columns or {}
    json_text_columns = json_text_columns or {}

    try:
        engine = get_sqlalchemy_engine(active_db)
        for group_name, tables in groups.items():
            if group_name:
                st.markdown(f"**{group_name}**")
            for table_name, description in tables.items():
                with st.expander(f"`{table_name}` — {description}", expanded=False):
                    try:
                        ident = _quoted(table_name)
                        limit = min(int(row_limit_overrides.get(table_name, row_limit)), MAX_ROW_LIMIT)
                        order_col = order_overrides.get(table_name)
                        if order_col:
                            order_sql = _quoted(order_col)
                            query = f"SELECT * FROM {ident} ORDER BY {order_sql} DESC LIMIT :lim"
                        else:
                            query = f"SELECT * FROM {ident} ORDER BY 1 DESC LIMIT :lim"
                        df_table = read_sql_df(engine, text(query), params={"lim": limit})
                        df_table = fix_uuid_columns(df_table)
                        df_table = _mask_columns(df_table, mask_columns.get(table_name, []))
                        df_table = _stringify_json_columns(
                            df_table, json_text_columns.get(table_name, [])
                        )
                        if df_table.empty:
                            st.info(f"Таблица `{table_name}` пуста.")
                        else:
                            height = min(max(len(df_table) * 35 + 60, 200), 400)
                            st.dataframe(
                                df_table,
                                width="stretch",
                                height=height,
                                hide_index=True,
                            )
                            st.caption(f"Показано {len(df_table)} записей из `{table_name}`")
                    except DataLoadError as e:
                        st.error(f"Не удалось загрузить `{table_name}`: {e}")
    except Exception as e:
        st.error(f"Не удалось подключиться для просмотра таблиц: {e}")

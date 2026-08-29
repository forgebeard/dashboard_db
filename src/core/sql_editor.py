# src/core/sql_editor.py
"""
Модуль глобального SQL-редактора.

Отвечает за выполнение пользовательских ad-hoc запросов к активной БД,
безопасное отображение результатов и историю запросов.
Предназначен для оффлайн-использования доверенными инженерами L2/L3.
"""

import time

import streamlit as st
from sqlalchemy import text

from core.config import MAX_ROW_LIMIT, statement_timeout_ms
from core.db_utils import get_sqlalchemy_engine, read_sql_df
from core.exceptions import DataLoadError, format_load_error
from core.sql_guard import apply_max_row_limit, validate_adhoc_sql
from core.ui_utils import fix_uuid_columns

_MAX_HISTORY_SIZE = 10
_WARNING_ROW_THRESHOLD = 1000


def _ensure_history() -> None:
    if "sql_history" not in st.session_state:
        st.session_state["sql_history"] = []


def _add_to_history(query: str) -> None:
    _ensure_history()
    history: list[str] = st.session_state["sql_history"]
    history = [q for q in history if q != query]
    history.insert(0, query)
    st.session_state["sql_history"] = history[:_MAX_HISTORY_SIZE]


def _format_sql_error(exc: Exception) -> str:
    return f"Ошибка выполнения: {format_load_error(exc)}"


def render_global_sql(active_db: str) -> None:
    """
    Отрисовывает SQL-редактор (поле, история, результат).
    Заголовок секции задаёт вызывающий код (expander в app.py).
    """
    st.caption(
        f"Только SELECT/WITH. Результат ограничен {MAX_ROW_LIMIT} строками. "
        f"Сессия PostgreSQL — read-only, statement_timeout {statement_timeout_ms() // 1000} с."
    )
    _ensure_history()

    col_query, col_btn = st.columns([5, 1])

    with col_query:
        global_query = st.text_area(
            "SQL Запрос:",
            placeholder="SELECT * FROM vm_static LIMIT 10;",
            key="global_sql_input_main",
            label_visibility="collapsed",
            height=80,
        )

    with col_btn:
        run_sql = st.button(
            "Выполнить",
            type="primary",
            width="stretch",
            disabled=not global_query.strip(),
        )

    history: list[str] = st.session_state.get("sql_history", [])
    if history:
        cols_hist = st.columns(len(history) + 1)
        for i, saved_query in enumerate(history):
            label = saved_query[:40].replace("\n", " ") + ("..." if len(saved_query) > 40 else "")
            if cols_hist[i].button(label, key=f"hist_{i}", help=saved_query):
                st.session_state["global_sql_input_main"] = saved_query
                st.rerun()

        if cols_hist[-1].button(":material/delete:", key="clear_history", help="Очистить историю"):
            st.session_state["sql_history"] = []
            st.rerun()

    if run_sql and global_query.strip():
        try:
            safe_sql = validate_adhoc_sql(global_query)
            limited_sql = apply_max_row_limit(safe_sql, MAX_ROW_LIMIT)
            engine = get_sqlalchemy_engine(active_db)

            start_time = time.perf_counter()
            df_res = read_sql_df(engine, text(limited_sql))
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            _add_to_history(global_query.strip())
            df_res = fix_uuid_columns(df_res)

            if df_res.empty:
                st.info(f"Запрос выполнен за {elapsed_ms:.0f} мс. Данных нет.")
            else:
                if len(df_res) >= MAX_ROW_LIMIT:
                    st.warning(
                        f"Показаны первые {MAX_ROW_LIMIT} строк. "
                        "Добавьте свой LIMIT или сузьте фильтр."
                    )
                elif len(df_res) > _WARNING_ROW_THRESHOLD:
                    st.warning(
                        f"Результат содержит {len(df_res)} строк. "
                        "Рекомендуется добавить LIMIT в запрос."
                    )

                st.caption(f"Найдено строк: **{len(df_res)}** | Время: **{elapsed_ms:.0f} мс**")

                st.dataframe(
                    df_res,
                    width="stretch",
                    height=400,
                    hide_index=True,
                )

        except ValueError as e:
            st.error(str(e))
        except DataLoadError as e:
            st.error(_format_sql_error(e))

# src/core/sql_editor.py
"""
Модуль глобального SQL-редактора.

Отвечает за выполнение пользовательских ad-hoc запросов к активной БД,
безопасное отображение результатов и историю запросов.
Предназначен для оффлайн-использования доверенными инженерами L2/L3.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text

from core.config import MAX_ROW_LIMIT
from core.db_utils import get_sqlalchemy_engine, read_sql_df
from core.exceptions import DataLoadError, format_load_error
from core.sql_guard import apply_max_row_limit, validate_adhoc_sql
from core.ui_utils import dataframe_height, fix_uuid_columns

logger = logging.getLogger(__name__)

_MAX_HISTORY_SIZE = 10
_WARNING_ROW_THRESHOLD = 1000
_SQL_INPUT_KEY = "global_sql_input_main"
_HISTORY_KEY = "sql_history"
_HISTORY_DB_KEY = "sql_history_db"
_HISTORY_SELECT_KEY = "sql_history_pick"
_LAST_RESULT_KEY = "sql_last_result"
_HISTORY_PLACEHOLDER = ""
_EDITOR_HEIGHT = 200
_HISTORY_LABEL_LEN = 40
_HISTORY_FILE = "sql_history.json"


def next_history(
    history: list[str], query: str, *, max_size: int = _MAX_HISTORY_SIZE
) -> list[str]:
    """Дедуп + вставка в начало, обрезка по max_size."""
    stripped = query.strip()
    if not stripped:
        return list(history)
    updated = [q for q in history if q != stripped]
    updated.insert(0, stripped)
    return updated[:max_size]


def load_history_query(
    state: Any, query: str, *, input_key: str = _SQL_INPUT_KEY
) -> None:
    """Подставляет SQL в ключ поля. Вызывать из колбэка, не после text_area."""
    if query:
        state[input_key] = query


def build_last_result(df: pd.DataFrame, elapsed_ms: float) -> dict[str, Any]:
    n = len(df)
    return {
        "df": df,
        "elapsed_ms": elapsed_ms,
        "row_count": n,
        "empty": df.empty,
        "truncated": n >= MAX_ROW_LIMIT,
        "large": n > _WARNING_ROW_THRESHOLD and n < MAX_ROW_LIMIT,
    }


def history_file_path() -> Path:
    return Path(__file__).resolve().parents[2] / "logs" / _HISTORY_FILE


def _normalize_queries(raw: object, *, max_size: int = _MAX_HISTORY_SIZE) -> list[str]:
    if not isinstance(raw, list):
        return []
    queries: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if stripped:
            queries.append(stripped)
        if len(queries) >= max_size:
            break
    return queries


def load_history_file(path: Path, db_name: str) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Не удалось прочитать историю SQL %s: %s", path, exc)
        return []
    if not isinstance(payload, dict):
        return []
    return _normalize_queries(payload.get(db_name, []))


def save_history_file(path: Path, db_name: str, queries: list[str]) -> None:
    normalized = _normalize_queries(queries)
    payload: dict[str, Any] = {}
    try:
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("История SQL будет перезаписана (%s): %s", path, exc)
    payload[db_name] = normalized
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix="sql_history_", suffix=".json", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_name, path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        logger.warning("Не удалось сохранить историю SQL %s: %s", path, exc)


def _ensure_history(active_db: str) -> None:
    if (
        _HISTORY_KEY not in st.session_state
        or st.session_state.get(_HISTORY_DB_KEY) != active_db
    ):
        st.session_state[_HISTORY_KEY] = load_history_file(
            history_file_path(), active_db
        )
        st.session_state[_HISTORY_DB_KEY] = active_db


def _add_to_history(query: str, db_name: str) -> None:
    _ensure_history(db_name)
    updated = next_history(st.session_state[_HISTORY_KEY], query)
    st.session_state[_HISTORY_KEY] = updated
    save_history_file(history_file_path(), db_name, updated)


def _clear_history() -> None:
    st.session_state[_HISTORY_KEY] = []
    st.session_state[_HISTORY_SELECT_KEY] = _HISTORY_PLACEHOLDER
    db_name = st.session_state.get(_HISTORY_DB_KEY) or st.session_state.get("active_db")
    if db_name:
        save_history_file(history_file_path(), str(db_name), [])


def _format_sql_error(exc: Exception) -> str:
    return f"Ошибка выполнения: {format_load_error(exc)}"


def _history_label(query: str) -> str:
    if not query:
        return "История"
    compact = " ".join(query.split())
    if len(compact) > _HISTORY_LABEL_LEN:
        return compact[:_HISTORY_LABEL_LEN] + "..."
    return compact


def _on_history_pick() -> None:
    query = st.session_state.get(_HISTORY_SELECT_KEY) or _HISTORY_PLACEHOLDER
    load_history_query(st.session_state, query)
    st.session_state[_HISTORY_SELECT_KEY] = _HISTORY_PLACEHOLDER


def _render_last_result(result: dict[str, Any]) -> None:
    elapsed_ms = result["elapsed_ms"]
    row_count = result["row_count"]
    df_res: pd.DataFrame = result["df"]

    if result["empty"]:
        st.info(f"Запрос выполнен за {elapsed_ms:.0f} мс. Данных нет.")
        return

    if result["truncated"]:
        st.warning(
            f"Показаны первые {MAX_ROW_LIMIT} строк. "
            "Добавьте свой LIMIT или сузьте фильтр."
        )
    elif result["large"]:
        st.warning(
            f"Результат содержит {row_count} строк. "
            "Рекомендуется добавить LIMIT в запрос."
        )

    st.caption(f"Найдено строк: **{row_count}** | Время: **{elapsed_ms:.0f} мс**")
    st.dataframe(
        df_res,
        width="stretch",
        height=dataframe_height(len(df_res)),
        hide_index=True,
    )


def render_global_sql(active_db: str) -> None:
    """
    Отрисовывает SQL-редактор (поле, история, результат).
    Заголовок секции задаёт вызывающий код (expander в app.py).
    """
    _ensure_history(active_db)
    history: list[str] = list(st.session_state.get(_HISTORY_KEY, []))
    history_options = [_HISTORY_PLACEHOLDER, *history]

    pick_col, clear_col, _ = st.columns(
        [2.4, 0.5, 5], vertical_alignment="bottom"
    )
    with pick_col:
        st.selectbox(
            "История",
            options=history_options,
            format_func=_history_label,
            key=_HISTORY_SELECT_KEY,
            on_change=_on_history_pick,
            label_visibility="collapsed",
            help="Подставить запрос из истории в поле",
        )
    with clear_col:
        st.button(
            ":material/delete:",
            key="clear_history",
            help="Очистить историю",
            on_click=_clear_history,
            disabled=not history,
        )

    global_query = st.text_area(
        "SQL Запрос:",
        placeholder="SELECT * FROM vm_static LIMIT 10;",
        key=_SQL_INPUT_KEY,
        label_visibility="collapsed",
        height=_EDITOR_HEIGHT,
    )
    run_sql = st.button(
        "Выполнить",
        type="primary",
        disabled=not (global_query or "").strip(),
    )

    if run_sql and (global_query or "").strip():
        try:
            safe_sql = validate_adhoc_sql(global_query)
            limited_sql = apply_max_row_limit(safe_sql, MAX_ROW_LIMIT)
            engine = get_sqlalchemy_engine(active_db)

            start_time = time.perf_counter()
            df_res = read_sql_df(engine, text(limited_sql))
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            _add_to_history(global_query.strip(), active_db)
            df_res = fix_uuid_columns(df_res)
            st.session_state[_LAST_RESULT_KEY] = build_last_result(df_res, elapsed_ms)
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except DataLoadError as e:
            st.error(_format_sql_error(e))

    last = st.session_state.get(_LAST_RESULT_KEY)
    if last is not None:
        _render_last_result(last)

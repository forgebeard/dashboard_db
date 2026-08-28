# src/system/system_module.py
"""Раздел «Системные»: вкладки сессий, фенсинга, квот и трансферов."""

import streamlit as st

from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_page_header,
)
from system.system_diagnostics import render_system_diagnostics
from system.system_utils import (
    SYSTEM_TAB_LABELS,
    fence_agents_caption,
    fence_warning_needed,
    fetch_system_tab,
    filter_system_rows,
    get_system_summary,
)

SYSTEM_FILTER_DEFAULTS = {"sys_search": ""}
_TAB_ORDER = ("sessions", "fence", "quota", "transfers")


def render_system_list(active_db: str, cluster_meta: dict) -> None:
    summary = get_system_summary(active_db)
    header_box = st.container()

    show_clear = filters_are_active(SYSTEM_FILTER_DEFAULTS)
    if show_clear:
        search_col, clear_col = st.columns([3.4, 0.9], vertical_alignment="bottom")
    else:
        search_col = st.container()
        clear_col = None

    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / IP / ключ):",
            placeholder="Например: admin, ipmilan...",
            key="sys_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(
                SYSTEM_FILTER_DEFAULTS, key="sys_clear_filters"
            )

    host_count = len((cluster_meta or {}).get("hosts", {}))
    details = [
        f"версия {summary['schema_version']}",
        f"сессий: {summary['sessions_count']}",
        fence_agents_caption(summary["fence_configured"]),
        f"трансферов: {summary['active_transfers']}",
    ]
    with header_box:
        render_page_header("Системные", active_db, details=details)

    if fence_warning_needed(host_count, summary["fence_configured"]):
        st.warning("Хосты есть, но фенсинг не настроен!")
    st.caption(fence_agents_caption(summary["fence_configured"]))

    tabs = st.tabs([SYSTEM_TAB_LABELS[tab_id] for tab_id in _TAB_ORDER])
    for tab, tab_id in zip(tabs, _TAB_ORDER):
        with tab:
            _render_system_tab(active_db, tab_id, search_term)

    render_system_diagnostics(active_db)


def _render_system_tab(active_db: str, tab_id: str, search_term: str) -> None:
    raw_df = fetch_system_tab(active_db, tab_id)
    shown = filter_system_rows(raw_df, search_term.strip() if search_term else "")
    st.markdown(f"**Записей:** {len(shown)}")
    if shown.empty:
        st.info("Нет записей по выбранным критериям.")
        return
    st.dataframe(
        shown,
        width="stretch",
        hide_index=True,
        height=dataframe_height(len(shown)),
        column_config={
            "name": st.column_config.TextColumn("Объект", width="medium"),
            "status": st.column_config.TextColumn("Статус / значение", width="medium"),
            "details": st.column_config.TextColumn("Контекст", width="large"),
            "source": st.column_config.TextColumn("Источник", width="small"),
        },
    )

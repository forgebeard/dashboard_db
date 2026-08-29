"""Список хранилищ: фильтры, сводка, таблица и текстовый инспектор."""

import streamlit as st

from core.constants import storage_health_counts, storage_status_tone
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_page_header,
    style_status_column,
    try_load,
)
from storage.storage_utils import fetch_storage_data, process_storage_dataframe

STORAGE_FILTER_DEFAULTS = {
    "storage_dc_filter": "Все ДЦ",
    "storage_search": "",
    "storage_health_filter": "all",
}


def render_storage_list(active_db, cluster_meta):
    dc_id_to_name = {
        str(k): v for k, v in (cluster_meta or {}).get("datacenters", {}).items()
    }
    dc_names_set = set(dc_id_to_name.values())

    header_box = st.container()
    show_clear = filters_are_active(STORAGE_FILTER_DEFAULTS)
    if show_clear:
        health_col, dc_col, search_col, clear_col = st.columns(
            [1.7, 1, 2.0, 0.9], vertical_alignment="bottom"
        )
    else:
        health_col, dc_col, search_col = st.columns(
            [1.7, 1, 2.4], vertical_alignment="bottom"
        )
        clear_col = None

    with dc_col:
        selected_dc_name = st.selectbox(
            "Дата-центр:",
            ["Все ДЦ"] + sorted(list(dc_names_set)),
            key="storage_dc_filter",
        )
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / UUID):",
            placeholder="Введите имя или UUID...",
            key="storage_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(
                STORAGE_FILTER_DEFAULTS, key="storage_clear_filters"
            )

    filters = (selected_dc_name, search_term)
    raw_df = try_load("хранилищ", fetch_storage_data, active_db, filters, dc_id_to_name)
    if raw_df is None:
        return
    counts = storage_health_counts(
        raw_df["shared_status_code"] if not raw_df.empty else []
    )

    health = "all"
    if not raw_df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("active", f"Active ({counts['active']})"),
                    ("problems", f"Остальное ({counts['problems']})"),
                ),
                key="storage_health_filter",
            )

    display_df = (
        process_storage_dataframe(raw_df, health_filter=health)
        if not raw_df.empty
        else raw_df
    )

    with header_box:
        render_page_header(
            "Хранилища",
            active_db,
            details=[f"{counts['total']} доменов"],
        )

    if raw_df.empty:
        st.info("Хранилища не найдены.")
        return
    if display_df.empty:
        st.info("Нет хранилищ, соответствующих выбранному состоянию.")
        return

    event = st.dataframe(
        style_status_column(display_df, storage_status_tone),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя домена": st.column_config.TextColumn(),
            "UUID": st.column_config.TextColumn(width=220),
            "Тип домена": st.column_config.TextColumn(width=120),
            "Тип хранилища": st.column_config.TextColumn(width=110),
            "Статус": st.column_config.TextColumn(width=110),
            "Дата-центр": st.column_config.TextColumn(width=120),
            "Заполнено (%)": st.column_config.ProgressColumn(
                "Заполнено", min_value=0, max_value=100, format="%f%%"
            ),
            "Всего (ГБ)": st.column_config.NumberColumn(width=90),
            "Свободно (ГБ)": st.column_config.NumberColumn(width=100),
            "_status_code": None,
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected = display_df.iloc[idx]
        selected_uuid = selected["UUID"]
        st.markdown(f"#### 🔍 Инспектор: {selected['Имя домена']}")
        st.caption(f"UUID: `{selected_uuid}` | ДЦ: {selected['Дата-центр']}")
        with st.spinner("Генерация полного отчета STORAGE-Inspector..."):
            from storage.storage_inspector_sql import get_storage_inspector_report

            result = get_storage_inspector_report(active_db, selected_uuid)
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

"""Список логических сетей: фильтры, таблица и текстовый инспектор."""

import streamlit as st

from core.exceptions import DataLoadError
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_load_error,
    render_page_header,
)
from networks.network_utils import fetch_networks_data, process_networks_dataframe

NET_FILTER_DEFAULTS = {
    "net_dc_filter": "Все ДЦ",
    "net_search": "",
}


def render_networks_list(active_db, cluster_meta):
    dc_map = {str(k): v for k, v in (cluster_meta or {}).get("datacenters", {}).items()}
    dc_names_set = set(dc_map.values())

    header_box = st.container()
    show_clear = filters_are_active(NET_FILTER_DEFAULTS)
    if show_clear:
        dc_col, search_col, clear_col = st.columns(
            [1.2, 2.4, 0.9], vertical_alignment="bottom"
        )
    else:
        dc_col, search_col = st.columns([1.2, 3.0], vertical_alignment="bottom")
        clear_col = None

    with dc_col:
        selected_dc = st.selectbox(
            "Дата-центр:",
            ["Все ДЦ"] + sorted(dc_names_set),
            key="net_dc_filter",
        )
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / VLAN / UUID):",
            placeholder="Введите имя, VLAN или UUID...",
            key="net_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(NET_FILTER_DEFAULTS, key="net_clear_filters")

    try:
        raw_df = fetch_networks_data(active_db, (selected_dc, search_term), dc_map)
    except DataLoadError as exc:
        render_load_error(exc, "сетей")
        return
    display_df = (
        process_networks_dataframe(raw_df, dc_map) if not raw_df.empty else raw_df
    )

    with header_box:
        render_page_header(
            "Сети",
            active_db,
            details=[f"{len(raw_df)} сетей"],
        )

    if raw_df.empty:
        st.info("Сети не найдены.")
        return
    if display_df.empty:
        st.info("Нет сетей, соответствующих критериям.")
        return

    event = st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя сети": st.column_config.TextColumn(),
            "UUID": st.column_config.TextColumn(width=220),
            "VLAN": st.column_config.TextColumn(width=90),
            "VM Network": st.column_config.CheckboxColumn(width=100),
            "MTU": st.column_config.NumberColumn(width=80),
            "Дата-центр": st.column_config.TextColumn(width=120),
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected = display_df.iloc[idx]
        st.markdown(f"#### 🔍 Инспектор сети: {selected['Имя сети']}")
        st.caption(
            f"UUID: `{selected['UUID']}` | ДЦ: {selected['Дата-центр']} | "
            f"VLAN: {selected['VLAN']}"
        )
        with st.spinner("Генерация отчета Network-Inspector..."):
            from networks.network_inspector_sql import get_network_inspector_report

            result = get_network_inspector_report(active_db, str(selected["UUID"]))
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

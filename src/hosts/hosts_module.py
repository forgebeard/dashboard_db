# src/hosts/hosts_module.py
"""Список хостов: фильтры, сводка, таблица и текстовый инспектор."""

import streamlit as st

from atlas.data_loader import release_key_from_meta
from core.constants import host_health_counts, host_status_tone
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_page_header,
    style_status_column,
    try_load,
)
from hosts.hosts_utils import fetch_hosts_data, process_host_dataframe

HOST_FILTER_DEFAULTS = {
    "host_dc_filter": "Все ДЦ",
    "host_cluster_filter": "Все кластеры",
    "host_search": "",
    "host_health_filter": "all",
}


def render_hosts_list(active_db, cluster_meta):
    clusters_raw = cluster_meta.get("clusters", {})
    clusters = {str(k): v for k, v in clusters_raw.items()}
    dc_id_to_name = {str(k): v for k, v in cluster_meta.get("datacenters", {}).items()}
    dc_to_clusters = {
        str(k): [str(x) for x in v]
        for k, v in cluster_meta.get("dc_to_clusters", {}).items()
    }
    dc_names_set = set(dc_id_to_name.values())

    header_box = st.container()
    show_clear = filters_are_active(HOST_FILTER_DEFAULTS)
    if show_clear:
        health_col, dc_col, cl_col, search_col, clear_col = st.columns(
            [1.7, 1, 1, 1.6, 0.9], vertical_alignment="bottom"
        )
    else:
        health_col, dc_col, cl_col, search_col = st.columns(
            [1.7, 1, 1, 2.0], vertical_alignment="bottom"
        )
        clear_col = None

    with dc_col:
        selected_dc_name = st.selectbox(
            "Дата-центр:",
            ["Все ДЦ"] + sorted(list(dc_names_set)),
            key="host_dc_filter",
        )
    with cl_col:
        cl_options = ["Все кластеры"]
        if selected_dc_name != "Все ДЦ":
            target_dc_id = next(
                (k for k, v in dc_id_to_name.items() if v == selected_dc_name), None
            )
            if target_dc_id and target_dc_id in dc_to_clusters:
                valid_cids = dc_to_clusters[target_dc_id]
                valid_names = [
                    clusters.get(cid, f"Cluster-{cid[:8]}") for cid in valid_cids
                ]
                cl_options += sorted(valid_names)
            else:
                cl_options += sorted(set(clusters.values()))
        else:
            cl_options += sorted(set(clusters.values()))
        selected_cluster_name = st.selectbox(
            "Кластер:", cl_options, key="host_cluster_filter"
        )
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / FQDN):",
            placeholder="Введите имя хоста или FQDN...",
            key="host_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(HOST_FILTER_DEFAULTS, key="host_clear_filters")

    filters = (selected_dc_name, selected_cluster_name, search_term)
    raw_df = try_load(
        "хостов", fetch_hosts_data, active_db, filters, clusters, dc_id_to_name
    )
    if raw_df is None:
        return
    counts = host_health_counts(raw_df["status_code"] if not raw_df.empty else [])

    health = "all"
    if not raw_df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("up", f"Up ({counts['up']})"),
                    ("maintenance", f"Maintenance ({counts['maintenance']})"),
                    ("problems", f"Остальное ({counts['problems']})"),
                ),
                key="host_health_filter",
            )

    display_df = (
        process_host_dataframe(raw_df, clusters, dc_id_to_name, health_filter=health)
        if not raw_df.empty
        else raw_df
    )

    with header_box:
        render_page_header(
            "Хосты",
            active_db,
            details=[f"{counts['total']} хостов"],
        )

    if raw_df.empty:
        st.info("Хосты не найдены.")
        return
    if display_df.empty:
        st.info("Нет хостов, соответствующих выбранному состоянию.")
        return

    event = st.dataframe(
        style_status_column(display_df, host_status_tone),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя хоста": st.column_config.TextColumn(),
            "FQDN": st.column_config.TextColumn(),
            "ID": st.column_config.TextColumn(width=220),
            "Статус": st.column_config.TextColumn(width=110),
            "SPM": st.column_config.TextColumn(
                width=70,
                help="Текущий Storage Pool Manager дата-центра (storage_pool.spm_vds_id)",
            ),
            "Активные ВМ": st.column_config.NumberColumn(width=90),
            "Кластер": st.column_config.TextColumn(width=120),
            "Дата-центр": st.column_config.TextColumn(width=120),
            "_status_code": None,
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected = display_df.iloc[idx]
        selected_id = selected["ID"]
        st.markdown(f"#### 🔍 Инспектор хоста: {selected['Имя хоста']}")
        st.caption(
            f"ID: `{selected_id}` | FQDN: {selected['FQDN']} | "
            f"Кластер: {selected['Кластер']} | ДЦ: {selected['Дата-центр']}"
        )
        with st.spinner("Генерация полного отчета Host-Inspector..."):
            from hosts.host_inspector_sql import get_host_inspector_report

            result = get_host_inspector_report(
                active_db,
                str(selected_id),
                release_key=release_key_from_meta(st.session_state.get("cluster_meta")),
            )
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

# src/vms/vms_module.py
"""Список ВМ: фильтры, сводка, таблица и текстовый инспектор."""

import streamlit as st

from core.constants import vm_health_counts, vm_layer_tone, vm_status_tone
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_page_header,
    style_status_column,
    try_load,
)
from vms.vms_utils import fetch_vms_data, process_vm_dataframe

VM_FILTER_DEFAULTS = {
    "vm_dc_filter": "Все ДЦ",
    "vm_cluster_filter": "Все кластеры",
    "vm_host_filter": "Все хосты",
    "vm_search": "",
    "vm_health_filter": "all",
}


def render_vms_list(active_db: str, cluster_meta: dict) -> None:
    clusters = {str(k): v for k, v in cluster_meta.get("clusters", {}).items()}
    hosts = {str(k): v for k, v in cluster_meta.get("hosts", {}).items()}
    dc_to_clusters = cluster_meta.get("dc_to_clusters", {})
    cluster_to_hosts = cluster_meta.get("cluster_to_hosts", {})
    dc_id_to_name = cluster_meta.get("datacenters", {})
    dc_names_set = set(dc_id_to_name.values())

    header_box = st.container()
    show_clear = filters_are_active(VM_FILTER_DEFAULTS)
    if show_clear:
        health_col, dc_col, cl_col, host_col, search_col, clear_col = st.columns(
            [2.2, 0.65, 0.85, 0.85, 1.2, 0.7], vertical_alignment="bottom"
        )
    else:
        health_col, dc_col, cl_col, host_col, search_col = st.columns(
            [2.2, 0.7, 0.9, 0.9, 1.4], vertical_alignment="bottom"
        )
        clear_col = None

    with dc_col:
        selected_dc_name = st.selectbox(
            "Дата-центр:",
            ["Все ДЦ"] + sorted(list(dc_names_set)),
            key="vm_dc_filter",
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
            "Кластер:", cl_options, key="vm_cluster_filter"
        )
    with host_col:
        h_options = ["Все хосты"]
        if selected_cluster_name != "Все кластеры":
            target_cid = next(
                (k for k, v in clusters.items() if v == selected_cluster_name), None
            )
            if target_cid and target_cid in cluster_to_hosts:
                valid_vids = cluster_to_hosts[target_cid]
                valid_names = [hosts.get(vid, f"Host-{vid[:8]}") for vid in valid_vids]
                h_options += sorted(valid_names)
            else:
                h_options += sorted(set(hosts.values()))
        else:
            h_options += sorted(set(hosts.values()))
        selected_host_name = st.selectbox("Хост:", h_options, key="vm_host_filter")
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / UUID):",
            placeholder="Введите имя или UUID...",
            key="vm_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(VM_FILTER_DEFAULTS, key="vm_clear_filters")

    filters = (selected_dc_name, selected_cluster_name, selected_host_name, search_term)
    raw_df = try_load(
        "ВМ", fetch_vms_data, active_db, filters, clusters, hosts, dc_id_to_name
    )
    if raw_df is None:
        return
    counts = vm_health_counts(
        raw_df["vm_status_code"] if not raw_df.empty else []
    )

    health = "all"
    if not raw_df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("up", f"Up ({counts['up']})"),
                    ("down", f"Down ({counts['down']})"),
                    ("problems", f"Остальное ({counts['problems']})"),
                ),
                key="vm_health_filter",
            )

    display_df = (
        process_vm_dataframe(
            raw_df, clusters, hosts, dc_id_to_name, health_filter=health
        )
        if not raw_df.empty
        else raw_df
    )

    with header_box:
        render_page_header(
            "Виртуальные машины",
            active_db,
            details=[f"{counts['total']} ВМ"],
        )

    if raw_df.empty:
        st.info("ВМ не найдены.")
        return
    if display_df.empty:
        st.info("Нет ВМ, соответствующих выбранному состоянию.")
        return

    event = st.dataframe(
        style_status_column(
            display_df,
            vm_status_tone,
            extra=(("Слои", "_layer_code", vm_layer_tone),),
        ),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя ВМ": st.column_config.TextColumn(),
            "UUID": st.column_config.TextColumn(width=220),
            "Статус": st.column_config.TextColumn(width=110),
            "Слои": st.column_config.TextColumn(width=100),
            "Хост": st.column_config.TextColumn(width=160),
            "Кластер": st.column_config.TextColumn(width=120),
            "Дата-центр": st.column_config.TextColumn(width=120),
            "_status_code": None,
            "_layer_code": None,
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected_uuid = display_df.iloc[idx]["UUID"]
        row = raw_df[raw_df["vm_guid"] == selected_uuid].iloc[0]
        st.markdown(f"#### Инспектор: {row['vm_name']}")
        st.caption(
            f"UUID: `{row['vm_guid']}` | Статус: {row.get('status_display', '—')}"
        )
        with st.spinner("Генерация полного отчета VM-Inspector..."):
            from vms.vm_inspector_sql import get_vm_inspector_report

            result = get_vm_inspector_report(active_db, str(row["vm_guid"]))
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

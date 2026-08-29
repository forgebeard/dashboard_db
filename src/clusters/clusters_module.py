# src/clusters/clusters_module.py
"""Список кластеров: фильтры, сводка, таблица и текстовый инспектор."""

import streamlit as st

from clusters.clusters_utils import fetch_clusters_data, process_cluster_dataframe
from core.constants import (
    cluster_health_counts,
    cluster_status_from_hosts,
    cluster_status_tone,
)
from core.exceptions import DataLoadError
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_load_error,
    render_page_header,
    style_status_column,
)

CLUSTER_FILTER_DEFAULTS = {
    "cluster_dc_filter": "Все ДЦ",
    "cluster_search": "",
    "cluster_health_filter": "all",
}


def render_clusters_list(active_db: str, cluster_meta: dict) -> None:
    dc_id_to_name = {
        str(k): v for k, v in cluster_meta.get("datacenters", {}).items()
    }
    dc_names_set = set(dc_id_to_name.values())

    header_box = st.container()
    show_clear = filters_are_active(CLUSTER_FILTER_DEFAULTS)
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
            key="cluster_dc_filter",
        )
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / UUID):",
            placeholder="Введите имя или UUID...",
            key="cluster_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(
                CLUSTER_FILTER_DEFAULTS, key="cluster_clear_filters"
            )

    filters = (selected_dc_name, search_term)
    try:
        raw_df = fetch_clusters_data(active_db, filters, dc_id_to_name)
    except DataLoadError as exc:
        render_load_error(exc, "кластеров")
        return
    if raw_df.empty:
        codes: list[int] = []
    else:
        codes = [
            cluster_status_from_hosts(problems, maintenance)
            for problems, maintenance in zip(
                raw_df.get("host_problems", []),
                raw_df.get("host_maintenance", []),
            )
        ]
    counts = cluster_health_counts(codes)

    health = "all"
    if not raw_df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("ok", f"Ok ({counts['ok']})"),
                    ("problems", f"Остальное ({counts['problems']})"),
                ),
                key="cluster_health_filter",
            )

    display_df = (
        process_cluster_dataframe(raw_df, dc_id_to_name, health_filter=health)
        if not raw_df.empty
        else raw_df
    )

    with header_box:
        render_page_header(
            "Кластеры",
            active_db,
            details=[f"{counts['total']} кластеров"],
        )

    if raw_df.empty:
        st.info("Кластеры не найдены.")
        return
    if display_df.empty:
        st.info("Нет кластеров, соответствующих выбранному состоянию.")
        return

    event = st.dataframe(
        style_status_column(display_df, cluster_status_tone),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя кластера": st.column_config.TextColumn(),
            "UUID": st.column_config.TextColumn(width=220),
            "Статус": st.column_config.TextColumn(width=110),
            "Хостов": st.column_config.NumberColumn(width=80),
            "Дата-центр": st.column_config.TextColumn(width=120),
            "_status_code": None,
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected = display_df.iloc[idx]
        selected_uuid = selected["UUID"]
        st.markdown(f"#### 🔍 Инспектор: {selected['Имя кластера']}")
        st.caption(
            f"UUID: `{selected_uuid}` | ДЦ: {selected['Дата-центр']}"
        )
        with st.spinner("Генерация полного отчета Cluster-Inspector..."):
            from clusters.cluster_inspector_sql import get_cluster_inspector_report

            result = get_cluster_inspector_report(active_db, str(selected_uuid))
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

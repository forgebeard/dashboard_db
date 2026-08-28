"""Список снапшотов: фильтры, сводка, таблица и текстовый инспектор."""

import streamlit as st

from core.constants import image_health_counts, image_status_tone
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_page_header,
    style_status_column,
)
from snapshots.snapshots_utils import (
    fetch_snapshots_data,
    prepare_snapshot_rows,
    process_snapshot_dataframe,
)

SNAP_FILTER_DEFAULTS = {
    "snap_dc_filter": "Все ДЦ",
    "snap_cluster_filter": "Все кластеры",
    "snap_search": "",
    "snap_health_filter": "all",
}


def render_snapshots_list(active_db: str, cluster_meta: dict) -> None:
    clusters_raw = cluster_meta.get("clusters", {})
    clusters = {str(k): v for k, v in clusters_raw.items()}
    dc_id_to_name = {str(k): v for k, v in cluster_meta.get("datacenters", {}).items()}
    dc_to_clusters = {
        str(k): [str(x) for x in v]
        for k, v in cluster_meta.get("dc_to_clusters", {}).items()
    }
    dc_names_set = set(dc_id_to_name.values())

    header_box = st.container()
    show_clear = filters_are_active(SNAP_FILTER_DEFAULTS)
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
            key="snap_dc_filter",
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
            "Кластер:", cl_options, key="snap_cluster_filter"
        )
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя ВМ / UUID):",
            placeholder="Введите имя или UUID...",
            key="snap_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(SNAP_FILTER_DEFAULTS, key="snap_clear_filters")

    filters = (selected_dc_name, selected_cluster_name, search_term)
    raw_df = fetch_snapshots_data(active_db, filters, dc_id_to_name, clusters)
    if raw_df.empty:
        counts = image_health_counts([])
    else:
        counts = image_health_counts(prepare_snapshot_rows(raw_df)["_status_code"])

    health = "all"
    if not raw_df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("ok", f"OK ({counts['ok']})"),
                    ("problems", f"Остальное ({counts['problems']})"),
                ),
                key="snap_health_filter",
            )

    display_df = (
        process_snapshot_dataframe(raw_df, health_filter=health)
        if not raw_df.empty
        else raw_df
    )

    with header_box:
        render_page_header(
            "Снапшоты",
            active_db,
            details=[f"{counts['total']} снапшотов"],
        )

    if raw_df.empty:
        st.info("Снапшоты не найдены.")
        return
    if display_df.empty:
        st.info("Нет снапшотов, соответствующих выбранному состоянию.")
        return

    event = st.dataframe(
        style_status_column(display_df, image_status_tone),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя ВМ": st.column_config.TextColumn(),
            "UUID снапшота": st.column_config.TextColumn(width=220),
            "Дата создания": st.column_config.DatetimeColumn(
                format="DD.MM.YYYY HH:mm", width=140
            ),
            "Тип": st.column_config.TextColumn(width=90),
            "Статус": st.column_config.TextColumn(width=90),
            "Размер": st.column_config.NumberColumn(format="%.2f ГБ", width=90),
            "Хранилище": st.column_config.TextColumn(width=120),
            "_status_code": None,
            "_vm_id": None,
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected = display_df.iloc[idx]
        vm_name = selected["Имя ВМ"]
        snap_id = selected["UUID снапшота"]
        snap_type = selected["Тип"]
        st.markdown(f"#### 🔍 Инспектор: {vm_name}")
        st.caption(
            f"ВМ UUID: `{selected['_vm_id']}` | снапшот: `{snap_id}` ({snap_type})"
        )
        with st.spinner("Генерация полного отчета Snapshot-Inspector..."):
            from snapshots.snapshot_inspector_sql import get_snapshot_inspector_report

            result = get_snapshot_inspector_report(
                active_db, str(selected["_vm_id"]), str(snap_id)
            )
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

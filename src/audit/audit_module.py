# src/audit/audit_module.py
"""Журнал событий: фильтры, pills важности и деталь по клику (без инспектора)."""

import streamlit as st

from core.constants import audit_health_counts, audit_severity_tone
from core.data_loader import host_ids_for_infra_filters
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_page_header,
    style_status_column,
    try_load,
)

from .audit_utils import (
    fetch_audit_logs,
    format_audit_event_detail,
    load_audit_infrastructure_maps,
    process_audit_dataframe,
)

AUDIT_FILTER_DEFAULTS = {
    "audit_dc": "Все ДЦ",
    "audit_cl": "Все кластеры",
    "audit_host": "Все хосты",
    "audit_search": "",
    "audit_start": None,
    "audit_end": None,
    "audit_lim": 500,
    "audit_health_filter": "all",
}


def render_audit_log(active_db, cluster_meta=None):
    maps = load_audit_infrastructure_maps(active_db, cluster_meta)

    header_box = st.container()
    show_clear = filters_are_active(AUDIT_FILTER_DEFAULTS)
    if show_clear:
        health_col, dc_col, cl_col, host_col, clear_col = st.columns(
            [1.7, 1, 1, 1, 0.9], vertical_alignment="bottom"
        )
    else:
        health_col, dc_col, cl_col, host_col = st.columns(
            [1.7, 1, 1, 1.4], vertical_alignment="bottom"
        )
        clear_col = None

    with dc_col:
        dc_opts = ["Все ДЦ"] + sorted(set(maps["dc_id_to_name"].values()))
        sel_dc = st.selectbox("Дата-центр", dc_opts, key="audit_dc")

    with cl_col:
        cl_opts = ["Все кластеры"]
        if sel_dc != "Все ДЦ":
            dc_id = next((k for k, v in maps["dc_id_to_name"].items() if v == sel_dc), None)
            valid_cls = [
                maps["cluster_id_to_name"][cid]
                for cid in maps["dc_to_clusters"].get(dc_id, [])
                if cid in maps["cluster_id_to_name"]
            ]
            cl_opts += sorted(valid_cls)
        else:
            cl_opts += sorted(set(maps["cluster_id_to_name"].values()))
        sel_cl = st.selectbox("Кластер", cl_opts, key="audit_cl")

    with host_col:
        h_opts = ["Все хосты"]
        if sel_cl != "Все кластеры":
            cl_id = next((k for k, v in maps["cluster_id_to_name"].items() if v == sel_cl), None)
            valid_hosts = [
                maps["host_id_to_name"][hid]
                for hid in maps["cluster_to_hosts"].get(cl_id, [])
                if hid in maps["host_id_to_name"]
            ]
            h_opts += sorted(valid_hosts)
        else:
            h_opts += sorted(set(maps["host_id_to_name"].values()))
        sel_host = st.selectbox("Хост", h_opts, key="audit_host")

    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(
                AUDIT_FILTER_DEFAULTS, key="audit_clear_filters"
            )

    search_col, start_col, end_col, limit_col = st.columns(
        [2.2, 1.4, 1.4, 0.8], vertical_alignment="bottom"
    )
    with search_col:
        search_term = st.text_input(
            "Поиск (событие / сообщение / ВМ)",
            placeholder="USER_ADD_VM, текст, имя или UUID...",
            key="audit_search",
        )
    with start_col:
        start_dt = st.datetime_input("С", value=None, key="audit_start")
    with end_col:
        end_dt = st.datetime_input("По", value=None, key="audit_end")
    with limit_col:
        limit_val = st.number_input("Лимит", 50, 10000, 500, step=50, key="audit_lim")

    host_ids = host_ids_for_infra_filters(maps, sel_dc, sel_cl, sel_host)
    filters = {
        "host_ids": None if host_ids is None else tuple(host_ids),
        "search": search_term.strip() if search_term else None,
        "start_dt": start_dt,
        "end_dt": end_dt,
    }

    df = try_load("журнала событий", fetch_audit_logs, active_db, filters, limit_val)
    if df is None:
        return
    counts = audit_health_counts(df["severity"] if not df.empty else [])

    health = "all"
    if not df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("warning", f"Warning ({counts['warning']})"),
                    ("errors", f"Error+Alert ({counts['errors']})"),
                ),
                key="audit_health_filter",
            )

    display_df = process_audit_dataframe(df, health_filter=health) if not df.empty else df

    with header_box:
        render_page_header(
            "Журнал событий",
            active_db,
            details=[f"{counts['total']} записей"],
        )

    if df.empty:
        st.info("Нет записей по заданным критериям.")
        return
    if display_df.empty:
        st.info("Нет записей, соответствующих выбранной важности.")
        return

    event = st.dataframe(
        style_status_column(display_df, audit_severity_tone, status_col="Ур."),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=dataframe_height(len(display_df)),
        column_config={"_status_code": None},
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        # display_df — срез raw df с тем же порядком строк после фильтра pills
        selected_raw = df.loc[display_df.index[idx]]
        st.markdown("#### Событие")
        st.code(format_audit_event_detail(selected_raw), language="text")

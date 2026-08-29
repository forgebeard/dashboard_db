# src/tasks/tasks_module.py
"""Список async-задач: фильтры, pills и сущности задачи по клику."""

import streamlit as st
from sqlalchemy import text

from audit.audit_utils import load_audit_infrastructure_maps
from core.constants import (
    async_task_bucket_tone,
    async_task_health_counts,
    async_task_result_tone,
)
from core.data_loader import host_ids_for_infra_filters
from core.db_utils import load_sql_df
from core.exceptions import DataLoadError
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_load_error,
    render_page_header,
    style_status_column,
    try_load,
)

from .tasks_utils import (
    build_audit_correlation_sql,
    build_task_entities_sql,
    build_tasks_list_sql,
    process_task_entities,
    process_tasks_dataframe,
)

TASK_FILTER_DEFAULTS = {
    "task_dc": "Все ДЦ",
    "task_cl": "Все кластеры",
    "task_host": "Все хосты",
    "task_vm_search": "",
    "task_start": None,
    "task_end": None,
    "task_id_search": "",
    "task_health_filter": "all",
}


def render_tasks_list(active_db, cluster_meta=None):
    maps = load_audit_infrastructure_maps(active_db, cluster_meta)

    header_box = st.container()
    show_clear = filters_are_active(TASK_FILTER_DEFAULTS)
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
        sel_dc = st.selectbox("Дата-центр", dc_opts, key="task_dc")

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
        sel_cl = st.selectbox("Кластер", cl_opts, key="task_cl")

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
        sel_host = st.selectbox("Хост", h_opts, key="task_host")

    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(TASK_FILTER_DEFAULTS, key="task_clear_filters")

    search_col, start_col, end_col, id_col = st.columns(
        [1.6, 1.2, 1.2, 1.4], vertical_alignment="bottom"
    )
    with search_col:
        search_vm = st.text_input(
            "Поиск ВМ (имя)", placeholder="Например: zabbix...", key="task_vm_search"
        )
    with start_col:
        start_dt = st.datetime_input("С даты", value=None, key="task_start")
    with end_col:
        end_dt = st.datetime_input("По дату", value=None, key="task_end")
    with id_col:
        search_id = st.text_input(
            "Поиск по Task ID", placeholder="UUID задачи...", key="task_id_search"
        )

    host_ids = host_ids_for_infra_filters(maps, sel_dc, sel_cl, sel_host)
    vm_term = search_vm.strip() if search_vm else None

    allowed_correlation_ids = None
    if host_ids is not None or vm_term:
        if host_ids == []:
            allowed_correlation_ids = []
        else:
            audit_sql, audit_params = build_audit_correlation_sql(
                host_ids=host_ids,
                vm_search=vm_term,
                start_dt=start_dt,
                end_dt=end_dt,
            )
            try:
                df_corr = load_sql_df(active_db, text(audit_sql), params=audit_params)
                allowed_correlation_ids = (
                    df_corr["correlation_id"].tolist() if not df_corr.empty else []
                )
            except DataLoadError as exc:
                render_load_error(exc, "фильтра по хостам/ВМ")
                allowed_correlation_ids = []

    sql, params = build_tasks_list_sql(
        allowed_correlation_ids=allowed_correlation_ids,
        start_dt=start_dt,
        end_dt=end_dt,
        search_id=search_id.strip() if search_id else None,
        limit=500,
    )

    df = try_load("задач", load_sql_df, active_db, sql, params=params)
    if df is None:
        return

    pairs = (
        list(zip(df["status"], df["result"])) if not df.empty else []
    )
    counts = async_task_health_counts(pairs)

    health = "all"
    if not df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("running", f"running ({counts['running']})"),
                    ("finished", f"finished ({counts['finished']})"),
                    ("errors", f"ошибки ({counts['errors']})"),
                ),
                key="task_health_filter",
            )

    show_df = process_tasks_dataframe(df, health_filter=health) if not df.empty else df

    with header_box:
        render_page_header(
            "Задачи",
            active_db,
            details=[f"{counts['total']} задач"],
        )

    if df.empty:
        st.info("Задач не найдено по заданным критериям.")
        return
    if show_df.empty:
        st.info("Нет задач, соответствующих выбранному состоянию.")
        return

    event = st.dataframe(
        style_status_column(
            show_df,
            async_task_bucket_tone,
            extra=[("Результат", "_result_code", async_task_result_tone)],
        ),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=dataframe_height(len(show_df)),
        column_config={
            "Начато": st.column_config.TextColumn(width=160),
            "Команда": st.column_config.TextColumn(width="medium"),
            "UUID": st.column_config.TextColumn(width=220),
            "correlation": st.column_config.TextColumn(width=220),
            "Статус": st.column_config.TextColumn(width=110),
            "Результат": st.column_config.TextColumn(width=120),
            "_status_code": None,
            "_result_code": None,
            "_vdsm_task_id": None,
        },
    )

    if not event.selection.rows:
        return

    idx = event.selection.rows[0]
    selected = show_df.iloc[idx]
    task_id = str(selected["UUID"])
    st.markdown(f"#### {selected['Команда']}")
    vdsm = selected.get("_vdsm_task_id") or "—"
    st.caption(
        f"Начато: {selected['Начато']} · "
        f"{selected['Статус']} / {selected['Результат']} · "
        f"UUID: `{task_id}` · command: `{selected['correlation']}` · "
        f"vdsm: `{vdsm}`"
    )
    ent_sql, ent_params = build_task_entities_sql(task_id)
    entities = try_load(
        "объектов задачи", load_sql_df, active_db, text(ent_sql), params=ent_params
    )
    if entities is None:
        return
    detail = process_task_entities(entities)
    if detail.empty:
        st.info("Объекты не привязаны.")
        return
    st.dataframe(
        detail,
        width="stretch",
        hide_index=True,
        height=dataframe_height(len(detail)),
    )

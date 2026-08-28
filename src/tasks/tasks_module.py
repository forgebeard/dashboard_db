# src/tasks/tasks_module.py
"""
Модуль отображения списка задач VDSM (UI).
Отвечает за: отрисовку фильтров (по ДЦ/Хосту/ВМ) и таблицы асинхронных задач.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st      # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd         # Работа с табличными данными и подготовка DataFrame для отображения

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from sqlalchemy import text

from core.db_utils import get_sqlalchemy_engine
from core.data_loader import host_ids_for_infra_filters
from core.ui_utils import dataframe_height
from audit.audit_utils import load_audit_infrastructure_maps
from .tasks_utils import (
    build_audit_correlation_sql,
    build_tasks_list_sql,
    format_tasks_dataframe,
)


def render_tasks_list(active_db, cluster_meta=None):
    maps = load_audit_infrastructure_maps(active_db, cluster_meta)

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])

    with c1:
        dc_opts = ["Все ДЦ"] + sorted(set(maps["dc_id_to_name"].values()))
        sel_dc = st.selectbox("Дата-центр", dc_opts, key="task_dc")

    with c2:
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

    with c3:
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

    with c4:
        search_vm = st.text_input(
            "Поиск ВМ (имя)", placeholder="Например: zabbix...", key="task_vm_search"
        )

    t1, t2, t3 = st.columns([2, 2, 2])
    with t1:
        start_dt = st.datetime_input("С даты", value=None, key="task_start")
    with t2:
        end_dt = st.datetime_input("По дату", value=None, key="task_end")
    with t3:
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
                engine_temp = get_sqlalchemy_engine(active_db)
                df_corr = pd.read_sql(text(audit_sql), engine_temp, params=audit_params)
                allowed_correlation_ids = (
                    df_corr["correlation_id"].tolist() if not df_corr.empty else []
                )
            except Exception:
                allowed_correlation_ids = None

    sql, params = build_tasks_list_sql(
        allowed_correlation_ids=allowed_correlation_ids,
        start_dt=start_dt,
        end_dt=end_dt,
        search_id=search_id.strip() if search_id else None,
        limit=500,
    )

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(sql, engine, params=params)

        if df.empty:
            st.info("Задач не найдено по заданным критериям.")
            return

        show_df = format_tasks_dataframe(df)
        st.dataframe(
            show_df,
            width="stretch",
            hide_index=True,
            height=dataframe_height(len(show_df)),
            column_config={
                "Начато": st.column_config.TextColumn(width=160),
                "Команда": st.column_config.TextColumn(width="medium"),
                "Статус": st.column_config.TextColumn(width=110),
                "Результат": st.column_config.TextColumn(width=120),
            },
        )

    except Exception as e:
        st.error(f"Ошибка загрузки задач: {e}")
        st.exception(e)

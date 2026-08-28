# src/audit/audit_module.py
"""
Модуль отображения журнала событий (Audit Log UI).
Отвечает за: отрисовку каскадных фильтров, таблицы логов и поиск по ВМ/Хостам.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st      # Фреймворк для построения веб-интерфейса дашборда

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from .audit_utils import (
    load_audit_infrastructure_maps,  # Загрузка связей ДЦ/Кластеры/Хосты для каскадных фильтров
    fetch_audit_logs                 # Выполнение параметризованного SQL-запроса к audit_log
)
from core.constants import (
    AUDIT_SEVERITY_ALERT,
    AUDIT_SEVERITY_ERROR,
    AUDIT_SEVERITY_WARNING,
    audit_severity_label,
    audit_severity_tone,
)
from core.data_loader import host_ids_for_infra_filters
from core.ui_utils import dataframe_height, style_status_column


def render_audit_log(active_db, cluster_meta=None):
    maps = load_audit_infrastructure_maps(active_db, cluster_meta)

    # --- СТРОКА 1: ФИЛЬТРЫ ИНФРАСТРУКТУРЫ И ПОИСК ---
    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])

    with c1:
        dc_opts = ["Все ДЦ"] + sorted(set(maps["dc_id_to_name"].values()))
        sel_dc = st.selectbox("Дата-центр", dc_opts, key="audit_dc")

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
        sel_cl = st.selectbox("Кластер", cl_opts, key="audit_cl")

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
        sel_host = st.selectbox("Хост", h_opts, key="audit_host")

    with c4:
        search_vm = st.text_input(
            "Поиск ВМ (имя/UUID)",
            placeholder="Например: tsk1-zabbix...",
            key="audit_vm_search",
        )

    t1, t2, t3, t4 = st.columns([2, 2, 1, 1])
    with t1:
        start_dt = st.datetime_input("С", value=None, key="audit_start")
    with t2:
        end_dt = st.datetime_input("По", value=None, key="audit_end")
    with t3:
        sev_map = {
            "Все": None,
            "Warning": AUDIT_SEVERITY_WARNING,
            "Error": AUDIT_SEVERITY_ERROR,
            "Alert": AUDIT_SEVERITY_ALERT,
        }
        sel_sev = st.selectbox("Важность", list(sev_map.keys()), key="audit_sev")
    with t4:
        limit_val = st.number_input("Лимит", 50, 10000, 500, step=50, key="audit_lim")

    host_ids = host_ids_for_infra_filters(maps, sel_dc, sel_cl, sel_host)
    filters = {
        "host_ids": None if host_ids is None else tuple(host_ids),
        "vm_search": search_vm.strip() if search_vm else None,
        "severity_code": sev_map[sel_sev],
        "start_dt": start_dt,
        "end_dt": end_dt,
    }

    df = fetch_audit_logs(active_db, filters, limit_val)

    if df.empty:
        st.info("Нет записей по заданным критериям.")
        return

    show_df = df[
        ["log_time", "log_type_name", "severity", "message", "vds_name", "vm_name", "user_name"]
    ].copy()
    show_df["_status_code"] = show_df["severity"]
    show_df["severity"] = show_df["_status_code"].map(audit_severity_label)
    show_df = show_df.rename(
        columns={
            "log_time": "Время",
            "log_type_name": "Событие",
            "severity": "Ур.",
            "message": "Сообщение",
            "vds_name": "Хост",
            "vm_name": "ВМ",
            "user_name": "User",
        }
    )

    st.dataframe(
        style_status_column(show_df, audit_severity_tone, status_col="Ур."),
        width="stretch",
        hide_index=True,
        height=dataframe_height(len(show_df)),
        column_config={"_status_code": None},
    )

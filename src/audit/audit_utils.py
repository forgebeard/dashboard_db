# src/audit/audit_utils.py
"""
Утилиты для работы с журналом событий (Audit Log).
"""

import pandas as pd
from sqlalchemy import text
import streamlit as st

from core.db_utils import get_sqlalchemy_engine
from core.data_loader import build_infra_filter_maps

def load_audit_infrastructure_maps(active_db, cluster_meta: dict | None = None):
    """Справочники фильтров: из cluster_meta, без полного скана audit_log."""
    if cluster_meta:
        return build_infra_filter_maps(cluster_meta)

    maps = build_infra_filter_maps({})
    try:
        engine = get_sqlalchemy_engine(active_db)
        df_dc_cl = pd.read_sql(text("""
            SELECT sp.id::text as dc_id, sp.name as dc_name,
                   c.cluster_id::text as cl_id, c.name as cl_name
            FROM storage_pool sp
            LEFT JOIN cluster c ON sp.id = c.storage_pool_id
        """), engine)
        for _, r in df_dc_cl.iterrows():
            dc_name = str(r["dc_name"]) if r["dc_name"] else f"DC-{str(r['dc_id'])[:8]}"
            cl_name = str(r["cl_name"]) if r["cl_name"] else f"Cluster-{str(r['cl_id'])[:8]}"
            maps["dc_id_to_name"][r["dc_id"]] = dc_name
            maps["cluster_id_to_name"][r["cl_id"]] = cl_name
            if r["cl_id"]:
                maps["dc_to_clusters"].setdefault(r["dc_id"], []).append(r["cl_id"])

        df_cl_host = pd.read_sql(text("""
            SELECT c.cluster_id::text as cl_id, v.vds_id::text as h_id, v.vds_name as h_name
            FROM cluster c
            LEFT JOIN vds_static v ON c.cluster_id = v.cluster_id
        """), engine)
        for _, r in df_cl_host.iterrows():
            host_name = str(r["h_name"]) if r["h_name"] else f"Host-{str(r['h_id'])[:8]}"
            maps["host_id_to_name"][r["h_id"]] = host_name
            if r["h_id"]:
                maps["cluster_to_hosts"].setdefault(r["cl_id"], []).append(r["h_id"])
    except Exception as e:
        st.warning(f"Не удалось загрузить связи для журнала: {e}")
    return maps


def build_audit_logs_sql(filters: dict, limit_val: int) -> tuple[str, dict]:
    """Параметризованный SELECT из audit_log. host_ids: None | [] | [id, ...]."""
    sql = """
        SELECT 
            audit_log_id, log_time, log_type_name, severity, message,
            vds_id::text, vds_name, vm_id::text, vm_name, user_name
        FROM audit_log
        WHERE deleted = false
    """
    params: dict = {}

    host_ids = filters.get("host_ids")
    if host_ids is not None:
        if not host_ids:
            sql += " AND 1=0"
        else:
            sql += " AND vds_id::text IN :host_ids"
            params["host_ids"] = tuple(host_ids)

    if filters.get("vm_search"):
        term = f"%{filters['vm_search']}%"
        sql += " AND (LOWER(vm_name) LIKE LOWER(:vm_term) OR vm_id::text LIKE LOWER(:vm_term))"
        params["vm_term"] = term

    if filters.get("severity_code") is not None:
        sql += " AND severity = :sev_code"
        params["sev_code"] = int(filters["severity_code"])

    if filters.get("start_dt"):
        sql += " AND log_time >= :start_dt"
        params["start_dt"] = filters["start_dt"]
    if filters.get("end_dt"):
        sql += " AND log_time <= :end_dt"
        params["end_dt"] = filters["end_dt"]

    sql += " ORDER BY log_time DESC LIMIT :lim"
    params["lim"] = limit_val
    return sql, params


@st.cache_data(ttl=60)
def fetch_audit_logs(active_db, filters, limit_val):
    """Выполняет параметризованный запрос к audit_log."""
    sql, params = build_audit_logs_sql(filters, limit_val)
    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(sql), engine, params=params)

        if not df.empty:
            df["log_time"] = pd.to_datetime(df["log_time"]).dt.strftime("%d.%m.%Y %H:%M:%S")
        return df
    except Exception as e:
        st.error(f"Ошибка чтения audit_log: {e}")
        return pd.DataFrame()

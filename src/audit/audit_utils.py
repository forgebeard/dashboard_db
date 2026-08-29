# src/audit/audit_utils.py
"""
Утилиты для работы с журналом событий (Audit Log).
"""

import pandas as pd
import streamlit as st
from sqlalchemy import text

from core.constants import (
    AUDIT_SEVERITY_ALERT,
    AUDIT_SEVERITY_ERROR,
    AUDIT_SEVERITY_WARNING,
    audit_severity_label,
)
from core.data_loader import build_infra_filter_maps
from core.db_utils import get_sqlalchemy_engine


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
            vds_id::text AS vds_id, vds_name,
            vm_id::text AS vm_id, vm_name,
            user_id::text AS user_id, user_name,
            correlation_id::text AS correlation_id,
            job_id::text AS job_id,
            cluster_id::text AS cluster_id, cluster_name,
            storage_domain_id::text AS storage_domain_id, storage_domain_name
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

    search = filters.get("search") or filters.get("vm_search")
    if search:
        term = f"%{search}%"
        sql += """ AND (
            LOWER(COALESCE(log_type_name, '')) LIKE LOWER(:q)
            OR LOWER(COALESCE(message, '')) LIKE LOWER(:q)
            OR LOWER(COALESCE(vm_name, '')) LIKE LOWER(:q)
            OR vm_id::text LIKE LOWER(:q)
        )"""
        params["q"] = term

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


def process_audit_dataframe(
    df: pd.DataFrame, health_filter: str = "all"
) -> pd.DataFrame:
    """Таблица журнала + фильтр по важности (pills)."""
    if df.empty:
        return pd.DataFrame()

    work = df.copy()
    if health_filter == "warning":
        work = work[work["severity"] == AUDIT_SEVERITY_WARNING]
    elif health_filter == "errors":
        work = work[work["severity"].isin([AUDIT_SEVERITY_ERROR, AUDIT_SEVERITY_ALERT])]
    if work.empty:
        return pd.DataFrame()

    show = work[
        [
            "log_time",
            "log_type_name",
            "severity",
            "message",
            "vds_name",
            "vm_name",
            "user_name",
        ]
    ].copy()
    show["_status_code"] = show["severity"]
    show["severity"] = show["_status_code"].map(audit_severity_label)
    return show.rename(
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


def format_audit_event_detail(row: pd.Series) -> str:
    """Полное сообщение и идентификаторы сущности по выбранной строке."""
    def _val(key: str) -> str:
        value = row.get(key)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        text = str(value).strip()
        return text if text and text.lower() != "none" else "—"

    lines = [
        _val("message"),
        "",
        f"Событие: {_val('log_type_name')}",
        f"user_id: {_val('user_id')}  ({_val('user_name')})",
        f"vm_id: {_val('vm_id')}  ({_val('vm_name')})",
        f"vds_id: {_val('vds_id')}  ({_val('vds_name')})",
        f"cluster_id: {_val('cluster_id')}  ({_val('cluster_name')})",
        f"storage_domain_id: {_val('storage_domain_id')}  ({_val('storage_domain_name')})",
        f"job_id: {_val('job_id')}",
        f"correlation_id: {_val('correlation_id')}",
        f"audit_log_id: {_val('audit_log_id')}",
    ]
    return "\n".join(lines)

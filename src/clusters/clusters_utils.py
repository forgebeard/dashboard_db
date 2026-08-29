# src/clusters/clusters_utils.py
"""
Утилиты для работы с данными кластеров.
Отвечает за: построение SQL-запросов и подготовку DataFrame для отображения.
Загрузка связей инфраструктуры централизована в core.data_loader.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from core.constants import (
    CLUSTER_STATUS_MAP,
    CLUSTER_STATUS_OK,
    CLUSTER_STATUS_PROBLEMS,
    HOST_MAINTENANCE_CODES,
    HOST_STATUS_UP,
    cluster_status_from_hosts,
)
from core.db_utils import load_sql_df

_MAINT_SQL = ", ".join(str(code) for code in sorted(HOST_MAINTENANCE_CODES))


def fetch_clusters_data(
    active_db: str,
    filters: tuple[str, str],
    dc_id_to_name: dict[str, str],
) -> pd.DataFrame:
    """SQL к кластерам: фильтры ДЦ/поиска и агрегаты статусов хостов."""
    selected_dc_name, search_term = filters

    target_dc_id = None
    if selected_dc_name != "Все ДЦ":
        target_dc_id = next(
            (k for k, v in dc_id_to_name.items() if v == selected_dc_name), None
        )

    base_sql = f"""
        SELECT
            c.cluster_id::text AS cluster_id,
            c.name,
            c.description,
            c.compatibility_version,
            c.storage_pool_id::text AS storage_pool_id,
            c.architecture,
            c.enable_balloon,
            c.enable_ksm,
            c.fencing_enabled,
            c.ha_reservation,
            COUNT(v.vds_id) AS host_count,
            COUNT(v.vds_id) FILTER (WHERE v.status = {HOST_STATUS_UP}) AS host_up,
            COUNT(v.vds_id) FILTER (
                WHERE v.status IN ({_MAINT_SQL})
            ) AS host_maintenance,
            COUNT(v.vds_id) FILTER (
                WHERE v.status IS NOT NULL
                  AND v.status <> {HOST_STATUS_UP}
                  AND v.status NOT IN ({_MAINT_SQL})
            ) AS host_problems
        FROM cluster c
        LEFT JOIN vds v ON c.cluster_id = v.cluster_id
        WHERE TRUE
    """

    conditions = []
    sql_params = {}

    if target_dc_id:
        conditions.append("c.storage_pool_id = :dc_id")
        sql_params["dc_id"] = target_dc_id

    if search_term:
        conditions.append(
            "(LOWER(c.name) LIKE LOWER(:search) OR c.cluster_id::text LIKE LOWER(:search))"
        )
        sql_params["search"] = f"%{search_term}%"

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)

    base_sql += """
        GROUP BY c.cluster_id, c.name, c.description, c.compatibility_version,
                 c.storage_pool_id, c.architecture, c.enable_balloon, c.enable_ksm,
                 c.fencing_enabled, c.ha_reservation
        ORDER BY c.name
    """

    return load_sql_df(
        active_db, text(base_sql), params=sql_params if sql_params else None
    )


def process_cluster_dataframe(
    df: pd.DataFrame,
    dc_id_to_name: dict[str, str],
    health_filter: str | None = None,
) -> pd.DataFrame:
    """Имена ДЦ, сводный статус по хостам, фильтр состояния."""
    if df.empty:
        return pd.DataFrame()

    df["dc_name"] = df["storage_pool_id"].map(dc_id_to_name).fillna("Unknown DC")
    for col in ("host_count", "host_up", "host_maintenance", "host_problems"):
        if col not in df.columns:
            df[col] = 0
        df[col] = df[col].fillna(0).astype(int)

    df["_status_code"] = [
        cluster_status_from_hosts(problems, maintenance)
        for problems, maintenance in zip(df["host_problems"], df["host_maintenance"])
    ]
    df["status_display"] = df["_status_code"].map(
        lambda code: CLUSTER_STATUS_MAP.get(code, f"Code {code}")
    )

    kind = health_filter or "all"
    if kind == "ok":
        df = df[df["_status_code"] == CLUSTER_STATUS_OK].copy()
    elif kind == "problems":
        df = df[df["_status_code"] == CLUSTER_STATUS_PROBLEMS].copy()

    display_df = df[
        [
            "name",
            "cluster_id",
            "status_display",
            "_status_code",
            "host_count",
            "dc_name",
        ]
    ].copy()
    display_df.columns = [
        "Имя кластера",
        "UUID",
        "Статус",
        "_status_code",
        "Хостов",
        "Дата-центр",
    ]
    return display_df

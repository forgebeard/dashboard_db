"""Утилиты списка доменов хранения: SQL и подготовка DataFrame."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
import streamlit as st

from core.db_utils import get_sqlalchemy_engine
from core.constants import (
    SHARED_STATUS_MAP,
    STORAGE_DOMAIN_TYPE_MAP,
    STORAGE_SHARED_ACTIVE,
    STORAGE_SHARED_UNATTACHED,
    STORAGE_TYPE_MAP,
    storage_is_problem,
)


def fetch_storage_data(
    active_db: str,
    filters: tuple[str, str],
    dc_id_to_name: dict[str, str],
) -> pd.DataFrame:
    """Загружает домены хранения с учётом фильтра ДЦ и поиска."""
    selected_dc_name, search_term = filters

    target_dc_id = None
    if selected_dc_name != "Все ДЦ":
        target_dc_id = next(
            (k for k, v in dc_id_to_name.items() if v == selected_dc_name), None
        )

    base_sql = """
        SELECT
            sds.id::text as sd_id,
            sds.storage_name,
            sds.storage_type,
            sds.storage_domain_type,
            COALESCE(sdd.used_disk_size, 0) as used_disk_size,
            COALESCE(sdd.available_disk_size, 0) as available_disk_size,
            COALESCE(sdss.status, 0) as shared_status_code,
            string_agg(DISTINCT sp.name, ', ' ORDER BY sp.name) as dc_name
        FROM storage_domain_static sds
        JOIN storage_domain_dynamic sdd ON sds.id = sdd.id
        LEFT JOIN storage_domain_shared_status sdss ON sds.id = sdss.storage_id
        LEFT JOIN storage_pool_iso_map spim ON sds.id = spim.storage_id
        LEFT JOIN storage_pool sp ON spim.storage_pool_id = sp.id
    """

    conditions = []
    sql_params: dict[str, object] = {}

    if target_dc_id:
        conditions.append("sp.id = :dc_id")
        sql_params["dc_id"] = target_dc_id

    if search_term:
        conditions.append(
            "(LOWER(sds.storage_name) LIKE LOWER(:search) OR sds.id::text LIKE LOWER(:search))"
        )
        sql_params["search"] = f"%{search_term}%"

    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)
    base_sql += """
        GROUP BY
            sds.id,
            sds.storage_name,
            sds.storage_type,
            sds.storage_domain_type,
            sdd.used_disk_size,
            sdd.available_disk_size,
            sdss.status
        ORDER BY sds.storage_name
    """

    try:
        engine = get_sqlalchemy_engine(active_db)
        return pd.read_sql(
            text(base_sql), engine, params=sql_params if sql_params else None
        )
    except Exception as e:
        st.error(f"Ошибка загрузки хранилищ: {e}")
        return pd.DataFrame()


def _resolve_health_filter(show_problems: bool, health_filter: str | None) -> str:
    if health_filter:
        return health_filter
    return "problems" if show_problems else "all"


def process_storage_dataframe(
    df: pd.DataFrame,
    show_problems: bool = False,
    health_filter: str | None = None,
) -> pd.DataFrame:
    """Маппинг типов/статусов, объём used+available, фильтр по состоянию."""
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["_status_code"] = df["shared_status_code"]
    df["domain_type_label"] = df["storage_domain_type"].map(
        lambda x: STORAGE_DOMAIN_TYPE_MAP.get(x, f"Code {x}")
    )
    df["storage_type_label"] = df["storage_type"].map(
        lambda x: STORAGE_TYPE_MAP.get(x, f"Code {x}")
    )
    df["status_label"] = df["shared_status_code"].map(
        lambda x: SHARED_STATUS_MAP.get(x, f"Code {x}")
    )
    df["dc_name"] = df["dc_name"].fillna("—")

    used_gb = pd.to_numeric(df["used_disk_size"], errors="coerce").fillna(0)
    free_gb = pd.to_numeric(df["available_disk_size"], errors="coerce").fillna(0)
    total_gb = used_gb + free_gb
    raw_pct = (used_gb / total_gb * 100).where(total_gb > 0, 0)
    df["used_pct"] = raw_pct.clip(lower=0, upper=100).round(1)
    df["total_gb"] = total_gb.round(0)
    df["free_gb"] = free_gb.round(0)
    df["is_problematic"] = df["shared_status_code"].map(storage_is_problem)

    kind = _resolve_health_filter(show_problems, health_filter)
    if kind == "active":
        df = df[df["shared_status_code"] == STORAGE_SHARED_ACTIVE].copy()
    elif kind == "unattached":
        df = df[df["shared_status_code"] == STORAGE_SHARED_UNATTACHED].copy()
    elif kind == "problems":
        df = df[df["is_problematic"]].copy()

    display_df = df[
        [
            "storage_name",
            "sd_id",
            "domain_type_label",
            "storage_type_label",
            "status_label",
            "_status_code",
            "dc_name",
            "used_pct",
            "total_gb",
            "free_gb",
        ]
    ].copy()
    display_df.columns = [
        "Имя домена",
        "UUID",
        "Тип домена",
        "Тип хранилища",
        "Статус",
        "_status_code",
        "Дата-центр",
        "Заполнено (%)",
        "Всего (ГБ)",
        "Свободно (ГБ)",
    ]
    return display_df

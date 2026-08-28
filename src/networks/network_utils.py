"""SQL и подготовка списка логических сетей."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
import streamlit as st

from core.db_utils import get_sqlalchemy_engine
from core.ui_utils import fix_uuid_columns


def fetch_networks_data(
    active_db: str,
    filters: tuple[str, str],
    dc_map: dict[str, str],
) -> pd.DataFrame:
    selected_dc, search_term = filters

    base_sql = """
        SELECT
            n.id::text AS id,
            n.name,
            n.description,
            n.vlan_id,
            n.vm_network,
            n.storage_pool_id::text AS storage_pool_id,
            n.mtu,
            n.stp,
            n.label
        FROM network n
        WHERE TRUE
    """
    conditions = []
    sql_params: dict[str, object] = {}

    if selected_dc != "Все ДЦ":
        dc_id = next((k for k, v in dc_map.items() if v == selected_dc), None)
        if dc_id:
            conditions.append("n.storage_pool_id = :dc_id")
            sql_params["dc_id"] = dc_id

    if search_term:
        conditions.append(
            "(LOWER(n.name) LIKE LOWER(:search) OR n.vlan_id::text LIKE LOWER(:search) "
            "OR LOWER(n.id::text) LIKE LOWER(:search))"
        )
        sql_params["search"] = f"%{search_term}%"

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
    base_sql += " ORDER BY n.name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(
            text(base_sql), engine, params=sql_params if sql_params else None
        )
        return fix_uuid_columns(df)
    except Exception as e:
        st.error(f"Ошибка загрузки сетей: {e}")
        return pd.DataFrame()


def process_networks_dataframe(
    df: pd.DataFrame,
    dc_map: dict[str, str],
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    work = df.copy()
    work["dc_name"] = work["storage_pool_id"].map(dc_map).fillna("—")
    work["vlan_display"] = work["vlan_id"].apply(
        lambda x: f"VLAN {x}" if x is not None and not (isinstance(x, float) and pd.isna(x)) else "—"
    )
    display = work[
        ["name", "id", "vlan_display", "vm_network", "mtu", "dc_name"]
    ].copy()
    display.columns = [
        "Имя сети",
        "UUID",
        "VLAN",
        "VM Network",
        "MTU",
        "Дата-центр",
    ]
    return display.reset_index(drop=True)

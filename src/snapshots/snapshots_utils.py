"""SQL и подготовка таблицы снапшотов: одна строка на snapshot_id."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
import streamlit as st

from core.constants import (
    IMAGE_LAYER_ISSUE_ORDER,
    IMAGE_STATUS_MAP,
    IMAGE_STATUS_OK,
    image_is_ok,
    image_is_problem,
    mapped_code_label,
)
from core.db_utils import get_sqlalchemy_engine


def fetch_snapshots_data(
    active_db: str,
    filters: tuple[str, str, str],
    dc_id_to_name: dict[str, str],
    clusters: dict[str, str],
) -> pd.DataFrame:
    """Снапшоты с образами (зерно — слой images) с учётом ДЦ, кластера и поиска."""
    selected_dc_name, selected_cluster_name, search_term = filters

    target_dc_id = None
    if selected_dc_name != "Все ДЦ":
        target_dc_id = next(
            (k for k, v in dc_id_to_name.items() if v == selected_dc_name), None
        )

    target_cid = None
    if selected_cluster_name != "Все кластеры":
        target_cid = next((k for k, v in clusters.items() if v == selected_cluster_name), None)

    base_sql = """
        SELECT
            s.snapshot_id::text AS snapshot_id,
            s.vm_id::text AS _vm_id,
            v.vm_name,
            s.creation_date,
            s.snapshot_type,
            i.image_guid::text AS image_guid,
            i.size,
            i.imagestatus AS _image_status_code,
            sd.storage_name
        FROM snapshots s
        JOIN vm_static v ON s.vm_id = v.vm_guid
        JOIN cluster c ON v.cluster_id = c.cluster_id
        LEFT JOIN storage_pool sp ON c.storage_pool_id = sp.id
        LEFT JOIN images i ON s.snapshot_id = i.vm_snapshot_id
        LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
        LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
        WHERE TRUE
    """

    conditions = []
    sql_params: dict[str, object] = {}

    if target_dc_id:
        conditions.append("c.storage_pool_id = :dc_id")
        sql_params["dc_id"] = target_dc_id

    if target_cid:
        conditions.append("v.cluster_id = :cluster_id")
        sql_params["cluster_id"] = target_cid

    if search_term:
        conditions.append(
            "(LOWER(v.vm_name) LIKE LOWER(:search) OR s.snapshot_id::text LIKE LOWER(:search))"
        )
        sql_params["search"] = f"%{search_term}%"

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)

    base_sql += " ORDER BY v.vm_name, s.creation_date"

    try:
        engine = get_sqlalchemy_engine(active_db)
        return pd.read_sql(
            text(base_sql), engine, params=sql_params if sql_params else None
        )
    except Exception as e:
        st.error(f"Ошибка загрузки снапшотов: {e}")
        return pd.DataFrame()


def _int_status(raw: object) -> int | None:
    if raw is None:
        return None
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _worst_image_status(codes: list[int | None]) -> int | None:
    present = {code for code in codes if code is not None}
    for code in IMAGE_LAYER_ISSUE_ORDER:
        if code in present:
            return code
    if IMAGE_STATUS_OK in present:
        return IMAGE_STATUS_OK
    return next(iter(present), None)


def _type_label(raw: object) -> str:
    if raw is None:
        return "—"
    try:
        if pd.isna(raw):
            return "—"
    except (TypeError, ValueError):
        pass
    text = str(raw).strip()
    return text if text else "—"


def prepare_snapshot_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Одна строка на snapshot_id: худший статус, сумма size."""
    if df.empty:
        return pd.DataFrame()

    records: list[dict] = []
    for snapshot_id, group in df.groupby("snapshot_id", sort=False, dropna=False):
        first = group.iloc[0]
        codes = [_int_status(v) for v in group["_image_status_code"]]
        sizes = pd.to_numeric(group["size"], errors="coerce")
        size_sum = float(sizes.sum()) if sizes.notna().any() else None
        storages = sorted(
            {
                str(name).strip()
                for name in group["storage_name"]
                if name not in (None, "") and not (isinstance(name, float) and pd.isna(name))
            }
        )
        records.append(
            {
                "snapshot_id": (
                    str(snapshot_id)
                    if snapshot_id is not None and not pd.isna(snapshot_id)
                    else ""
                ),
                "_vm_id": first["_vm_id"],
                "vm_name": first["vm_name"],
                "creation_date": first["creation_date"],
                "snapshot_type": first["snapshot_type"],
                "_status_code": _worst_image_status(codes),
                "size": size_sum,
                "storage_name": ", ".join(storages) if storages else "—",
            }
        )

    snap_df = pd.DataFrame.from_records(records)
    if snap_df.empty:
        return snap_df

    snap_df["_vm_sort"] = snap_df["vm_name"].astype(str).str.lower()
    snap_df = snap_df.sort_values(
        ["_vm_sort", "creation_date"], kind="mergesort"
    ).reset_index(drop=True)
    snap_df["type_label"] = snap_df["snapshot_type"].map(_type_label)
    snap_df["status_label"] = snap_df["_status_code"].map(
        lambda code: mapped_code_label(code, IMAGE_STATUS_MAP)
    )
    snap_df["size_gb"] = snap_df["size"].apply(
        lambda x: round(x / (1024**3), 2) if pd.notna(x) else None
    )
    return snap_df


def process_snapshot_dataframe(
    df: pd.DataFrame,
    health_filter: str = "all",
) -> pd.DataFrame:
    """Таблица для UI: одна строка на снапшот, фильтр по imagestatus."""
    if df.empty:
        return pd.DataFrame()

    snap_df = prepare_snapshot_rows(df)
    if snap_df.empty:
        return pd.DataFrame()

    if health_filter == "ok":
        snap_df = snap_df[snap_df["_status_code"].map(image_is_ok)].copy()
    elif health_filter == "problems":
        snap_df = snap_df[snap_df["_status_code"].map(image_is_problem)].copy()

    if snap_df.empty:
        return pd.DataFrame()

    display = pd.DataFrame(
        {
            "Имя ВМ": snap_df["vm_name"],
            "UUID снапшота": snap_df["snapshot_id"],
            "Дата создания": snap_df["creation_date"],
            "Тип": snap_df["type_label"],
            "Статус": snap_df["status_label"],
            "_status_code": snap_df["_status_code"],
            "Размер": snap_df["size_gb"],
            "Хранилище": snap_df["storage_name"],
            "_vm_id": snap_df["_vm_id"],
        }
    )
    return display.reset_index(drop=True)

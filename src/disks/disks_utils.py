"""SQL и подготовка списка дисков и образов."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
import streamlit as st

from core.constants import (
    IMAGE_STATUS_MAP,
    image_is_ok,
    image_is_problem,
    mapped_code_label,
)
from core.db_utils import get_sqlalchemy_engine
from core.ui_utils import fix_uuid_columns


def format_size_bytes(size_bytes):
    """Конвертирует байты в читаемый формат (ГБ)."""
    if size_bytes is None or pd.isna(size_bytes):
        return "—"
    try:
        gb = float(size_bytes) / (1024**3)
        return f"{gb:.2f} ГБ"
    except (ValueError, TypeError):
        return "—"


def fetch_disks_data(
    active_db: str,
    filters: tuple[str, str, str],
) -> pd.DataFrame:
    """Образы с поиском по диску, ВМ и домену. Статус в SQL не фильтруется."""
    search_disk, search_vm, search_sd = filters

    base_sql = """
        SELECT
            bd.disk_alias,
            i.image_guid::text,
            i.imagestatus,
            i.size,
            did.actual_size,
            i.active,
            vm.vm_name,
            sd.storage_name
        FROM images i
        JOIN base_disks bd ON i.image_group_id = bd.disk_id
        LEFT JOIN disk_image_dynamic did ON i.image_guid = did.image_id
        LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
        LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
        LEFT JOIN vm_device vd ON bd.disk_id = vd.device_id
        LEFT JOIN vm_static vm ON vd.vm_id = vm.vm_guid
        WHERE TRUE
    """

    conditions = []
    params: dict[str, object] = {}

    if search_disk:
        conditions.append(
            "(LOWER(bd.disk_alias) LIKE LOWER(:search_disk) "
            "OR i.image_guid::text LIKE LOWER(:search_disk))"
        )
        params["search_disk"] = f"%{search_disk}%"

    if search_vm:
        conditions.append("LOWER(vm.vm_name) LIKE LOWER(:search_vm)")
        params["search_vm"] = f"%{search_vm}%"

    if search_sd:
        conditions.append("LOWER(sd.storage_name) LIKE LOWER(:search_sd)")
        params["search_sd"] = f"%{search_sd}%"

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)

    if not any([search_disk, search_vm, search_sd]):
        base_sql += " ORDER BY i.creation_date DESC LIMIT 500"
    else:
        base_sql += " ORDER BY bd.disk_alias"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(
            text(base_sql), engine, params=params if params else None
        )
        return fix_uuid_columns(df)
    except Exception as e:
        st.error(f"Ошибка загрузки данных о дисках: {e}")
        return pd.DataFrame()


def process_disks_dataframe(
    df: pd.DataFrame,
    health_filter: str = "all",
) -> pd.DataFrame:
    """Статусы IMAGE_STATUS_MAP, фильтр по состоянию образа."""
    if df.empty:
        return pd.DataFrame()

    work = df.copy()
    work["_status_code"] = work["imagestatus"]
    if health_filter == "ok":
        work = work[work["_status_code"].map(image_is_ok)].copy()
    elif health_filter == "problems":
        work = work[work["_status_code"].map(image_is_problem)].copy()
    if work.empty:
        return pd.DataFrame()

    work["status_label"] = work["_status_code"].map(
        lambda code: mapped_code_label(code, IMAGE_STATUS_MAP)
    )
    work["virt_size_fmt"] = work["size"].apply(format_size_bytes)
    work["actual_size_fmt"] = work["actual_size"].apply(format_size_bytes)
    work["vm_name"] = work["vm_name"].fillna("—")
    work["storage_name"] = work["storage_name"].fillna("—")

    display_df = work[
        [
            "disk_alias",
            "image_guid",
            "status_label",
            "_status_code",
            "vm_name",
            "storage_name",
            "virt_size_fmt",
            "actual_size_fmt",
            "active",
        ]
    ].copy()
    display_df.columns = [
        "Имя диска",
        "UUID образа",
        "Статус",
        "_status_code",
        "ВМ",
        "Хранилище",
        "Вирт. размер",
        "Факт. размер",
        "Активен",
    ]
    return display_df.reset_index(drop=True)

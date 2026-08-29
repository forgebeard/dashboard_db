"""SQL и подготовка списка дисков и образов."""

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
            i.image_group_id::text AS disk_id,
            bd.disk_alias,
            i.image_guid::text,
            i.imagestatus,
            i.size,
            did.actual_size,
            i.active,
            string_agg(DISTINCT vm.vm_name, ', ') AS vm_name,
            string_agg(DISTINCT sd.storage_name, ', ') AS storage_name
        FROM images i
        JOIN base_disks bd ON i.image_group_id = bd.disk_id
        LEFT JOIN disk_image_dynamic did ON i.image_guid = did.image_id
        LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
        LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
        LEFT JOIN vm_device vd ON bd.disk_id = vd.device_id AND vd.type = 'disk'
        LEFT JOIN vm_static vm ON vd.vm_id = vm.vm_guid
        WHERE TRUE
    """

    no_search = not any([search_disk, search_vm, search_sd])
    if no_search:
        base_sql = base_sql.replace(
            "FROM images i\n        JOIN base_disks bd ON i.image_group_id = bd.disk_id",
            """FROM images i
        JOIN (
            SELECT image_group_id
            FROM images
            GROUP BY image_group_id
            ORDER BY MAX(creation_date) DESC
            LIMIT 500
        ) newest ON newest.image_group_id = i.image_group_id
        JOIN base_disks bd ON i.image_group_id = bd.disk_id""",
            1,
        )

    conditions = []
    params: dict[str, object] = {}

    if search_disk:
        conditions.append(
            "(LOWER(bd.disk_alias) LIKE LOWER(:search_disk) "
            "OR LOWER(i.image_group_id::text) LIKE LOWER(:search_disk) "
            "OR LOWER(i.image_guid::text) LIKE LOWER(:search_disk))"
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

    base_sql += """
        GROUP BY
            i.image_group_id,
            bd.disk_alias,
            i.image_guid,
            i.imagestatus,
            i.size,
            did.actual_size,
            i.active,
            i.creation_date
        ORDER BY bd.disk_alias
    """

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(
            text(base_sql), engine, params=params if params else None
        )
        return fix_uuid_columns(df)
    except Exception as e:
        st.error(f"Ошибка загрузки данных о дисках: {e}")
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


def _is_active(raw: object) -> bool:
    return raw in (True, 1, "1", "t", "true", "True")


def _name_set(series: pd.Series) -> str:
    names = sorted(
        {
            str(name).strip()
            for name in series
            if name not in (None, "") and not (isinstance(name, float) and pd.isna(name))
        }
    )
    return ", ".join(names) if names else "—"


def prepare_disk_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Одна строка на disk_id: худший imagestatus, размеры по слоям."""
    if df.empty:
        return pd.DataFrame()

    records: list[dict] = []
    for disk_id, group in df.groupby("disk_id", sort=False, dropna=False):
        layers = group.drop_duplicates(subset=["image_guid"], keep="first")
        first = layers.iloc[0]
        codes = [_int_status(v) for v in layers["imagestatus"]]
        worst = _worst_image_status(codes)

        inspect_guid = None
        if worst in IMAGE_LAYER_ISSUE_ORDER:
            for _, row in layers.iterrows():
                if _int_status(row["imagestatus"]) == worst:
                    inspect_guid = row["image_guid"]
                    break
        if inspect_guid in (None, ""):
            active_rows = layers[layers["active"].map(_is_active)]
            pick = active_rows.iloc[0] if not active_rows.empty else first
            inspect_guid = pick["image_guid"]

        active_rows = layers[layers["active"].map(_is_active)]
        virt_row = active_rows.iloc[0] if not active_rows.empty else first
        actual = pd.to_numeric(layers["actual_size"], errors="coerce")
        actual_sum = float(actual.sum()) if actual.notna().any() else None

        records.append(
            {
                "disk_id": (
                    str(disk_id)
                    if disk_id is not None and not pd.isna(disk_id)
                    else ""
                ),
                "disk_alias": first["disk_alias"],
                "_inspect_image_guid": inspect_guid,
                "_status_code": worst,
                "size": virt_row["size"],
                "actual_size": actual_sum,
                "vm_name": _name_set(group["vm_name"]),
                "storage_name": _name_set(group["storage_name"]),
            }
        )

    disk_df = pd.DataFrame.from_records(records)
    if disk_df.empty:
        return disk_df
    disk_df["status_label"] = disk_df["_status_code"].map(
        lambda code: mapped_code_label(code, IMAGE_STATUS_MAP)
    )
    disk_df["virt_size_fmt"] = disk_df["size"].apply(format_size_bytes)
    disk_df["actual_size_fmt"] = disk_df["actual_size"].apply(format_size_bytes)
    return disk_df.reset_index(drop=True)


def process_disks_dataframe(
    df: pd.DataFrame,
    health_filter: str = "all",
) -> pd.DataFrame:
    """Одна строка на диск, фильтр по худшему imagestatus."""
    if df.empty:
        return pd.DataFrame()

    disk_df = prepare_disk_rows(df)
    if disk_df.empty:
        return pd.DataFrame()

    if health_filter == "ok":
        disk_df = disk_df[disk_df["_status_code"].map(image_is_ok)].copy()
    elif health_filter == "problems":
        disk_df = disk_df[disk_df["_status_code"].map(image_is_problem)].copy()
    if disk_df.empty:
        return pd.DataFrame()

    display_df = disk_df[
        [
            "disk_alias",
            "disk_id",
            "status_label",
            "_status_code",
            "vm_name",
            "storage_name",
            "virt_size_fmt",
            "actual_size_fmt",
            "_inspect_image_guid",
        ]
    ].copy()
    display_df.columns = [
        "Имя диска",
        "UUID диска",
        "Статус",
        "_status_code",
        "ВМ",
        "Хранилище",
        "Вирт. размер",
        "Факт. размер",
        "_inspect_image_guid",
    ]
    return display_df.reset_index(drop=True)

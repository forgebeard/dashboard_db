"""SQL и подготовка таблицы снапшотов: одна строка на snapshot_id."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from core.constants import (
    IMAGE_LAYER_ISSUE_ORDER,
    IMAGE_STATUS_MAP,
    IMAGE_STATUS_OK,
    image_is_ok,
    image_is_problem,
    mapped_code_label,
)
from core.db_utils import get_sqlalchemy_engine, read_sql_df
from core.ui_utils import fix_uuid_columns

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _scope_filters(
    target_dc_id: str | None,
    target_cid: str | None,
    search_term: str,
) -> tuple[list[str], dict[str, object]]:
    parts: list[str] = []
    params: dict[str, object] = {"nil_uuid": NIL_UUID}
    if target_dc_id:
        parts.append("c.storage_pool_id = :dc_id")
        params["dc_id"] = target_dc_id
    if target_cid:
        parts.append("v.cluster_id = :cluster_id")
        params["cluster_id"] = target_cid
    if search_term:
        parts.append(
            "(LOWER(v.vm_name) LIKE LOWER(:search) "
            "OR LOWER(s.snapshot_id::text) LIKE LOWER(:search) "
            "OR LOWER(i.image_guid::text) LIKE LOWER(:search))"
        )
        params["search"] = f"%{search_term}%"
    return parts, params


def fetch_snapshots_data(
    active_db: str,
    filters: tuple[str, str, str],
    dc_id_to_name: dict[str, str],
    clusters: dict[str, str],
) -> pd.DataFrame:
    """Снапшоты и слои без строки snapshots (как в VM-Inspector)."""
    selected_dc_name, selected_cluster_name, search_term = filters

    target_dc_id = None
    if selected_dc_name != "Все ДЦ":
        target_dc_id = next(
            (k for k, v in dc_id_to_name.items() if v == selected_dc_name), None
        )

    target_cid = None
    if selected_cluster_name != "Все кластеры":
        target_cid = next((k for k, v in clusters.items() if v == selected_cluster_name), None)

    extra, sql_params = _scope_filters(target_dc_id, target_cid, search_term)
    extra_sql = (" AND " + " AND ".join(extra)) if extra else ""

    snap_sql = f"""
        SELECT
            s.snapshot_id::text AS snapshot_id,
            s.vm_id::text AS _vm_id,
            v.vm_name,
            s.creation_date,
            s.snapshot_type,
            i.image_guid::text AS image_guid,
            i.size,
            did.actual_size,
            i.imagestatus AS _image_status_code,
            sd.storage_name
        FROM snapshots s
        JOIN vm_static v ON s.vm_id = v.vm_guid
        JOIN cluster c ON v.cluster_id = c.cluster_id
        LEFT JOIN images i ON s.snapshot_id = i.vm_snapshot_id
        LEFT JOIN disk_image_dynamic did ON did.image_id = i.image_guid
        LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
        LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
        WHERE TRUE
        {extra_sql}
    """

    orphan_sql = f"""
        SELECT
            NULL::text AS snapshot_id,
            v.vm_guid::text AS _vm_id,
            v.vm_name,
            i.creation_date,
            NULL::text AS snapshot_type,
            i.image_guid::text AS image_guid,
            i.size,
            did.actual_size,
            i.imagestatus AS _image_status_code,
            sd.storage_name
        FROM images i
        JOIN base_disks bd ON i.image_group_id = bd.disk_id
        JOIN vm_device vd ON vd.device_id = bd.disk_id AND vd.type = 'disk'
        JOIN vm_static v ON v.vm_guid = vd.vm_id
        JOIN cluster c ON v.cluster_id = c.cluster_id
        LEFT JOIN snapshots s ON s.snapshot_id = i.vm_snapshot_id
        LEFT JOIN disk_image_dynamic did ON did.image_id = i.image_guid
        LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
        LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
        WHERE (
            s.snapshot_id IS NULL
            OR i.vm_snapshot_id IS NULL
            OR i.vm_snapshot_id::text = :nil_uuid
        )
        {extra_sql}
    """

    base_sql = f"""
        SELECT * FROM (
            {snap_sql}
            UNION
            {orphan_sql}
        ) snap_rows
        ORDER BY vm_name, creation_date
    """

    engine = get_sqlalchemy_engine(active_db)
    df = read_sql_df(engine, text(base_sql), params=sql_params)
    return fix_uuid_columns(df)


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


def _has_snapshot_id(raw: object) -> bool:
    if raw in (None, "", "—"):
        return False
    try:
        if pd.isna(raw):
            return False
    except (TypeError, ValueError):
        pass
    return str(raw).strip().lower() not in ("", NIL_UUID)


def _group_key(row: pd.Series) -> str:
    if _has_snapshot_id(row.get("snapshot_id")):
        return "s:" + str(row["snapshot_id"]).strip().lower()
    guid = row.get("image_guid")
    if guid not in (None, "") and not (isinstance(guid, float) and pd.isna(guid)):
        return "i:" + str(guid).strip().lower()
    return "empty"


def prepare_snapshot_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Одна строка на снапшот или на слой без снапшота."""
    if df.empty:
        return pd.DataFrame()

    work = df.copy()
    work["_grp"] = work.apply(_group_key, axis=1)

    records: list[dict] = []
    for _, group in work.groupby("_grp", sort=False, dropna=False):
        first = group.iloc[0]
        layers = group.drop_duplicates(subset=["image_guid"], keep="first")
        codes = [_int_status(v) for v in layers["_image_status_code"]]
        sizes = pd.to_numeric(layers["actual_size"], errors="coerce")
        size_sum = float(sizes.sum()) if sizes.notna().any() else None
        layer_ids = [
            str(guid).strip()
            for guid in layers["image_guid"]
            if guid not in (None, "") and not (isinstance(guid, float) and pd.isna(guid))
        ]
        storages = sorted(
            {
                str(name).strip()
                for name in group["storage_name"]
                if name not in (None, "") and not (isinstance(name, float) and pd.isna(name))
            }
        )
        snap_id = first["snapshot_id"]
        records.append(
            {
                "snapshot_id": (
                    str(snap_id).strip() if _has_snapshot_id(snap_id) else "—"
                ),
                "_vm_id": first["_vm_id"],
                "vm_name": first["vm_name"],
                "creation_date": first["creation_date"],
                "snapshot_type": first["snapshot_type"],
                "_status_code": _worst_image_status(codes),
                "size": size_sum,
                "layer_guids": ", ".join(layer_ids) if layer_ids else "—",
                "storage_name": ", ".join(storages) if storages else "—",
            }
        )

    snap_df = pd.DataFrame.from_records(records)
    if snap_df.empty:
        return snap_df

    snap_df["_vm_sort"] = snap_df["vm_name"].astype(str).str.lower()
    snap_df = snap_df.sort_values(
        ["_vm_sort", "creation_date"], kind="mergesort", na_position="last"
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
            "UUID слоёв": snap_df["layer_guids"],
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

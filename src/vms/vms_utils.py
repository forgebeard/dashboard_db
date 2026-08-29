# src/vms/vms_utils.py
"""
Утилиты для работы с данными ВМ.
Отвечает за: построение SQL-запросов и подготовку DataFrame для отображения.
Загрузка связей инфраструктуры теперь централизована в core.data_loader.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from core.constants import (
    IMAGE_LAYER_ISSUE_ORDER,
    IMAGE_STATUS_ILLEGAL,
    IMAGE_STATUS_LOCKED,
    IMAGE_STATUS_MAP,
    IMAGE_STATUS_MERGING,
    VM_STATUS_DOWN,
    VM_STATUS_MAP,
    VM_STATUS_UP,
    vm_is_problem,
)
from core.db_utils import get_sqlalchemy_engine, read_sql_df


def _layer_issue_codes(raw: object) -> list[int]:
    if raw is None:
        return []
    try:
        if pd.isna(raw):
            return []
    except (TypeError, ValueError):
        pass
    if isinstance(raw, str):
        text_val = raw.strip().strip("{}")
        if not text_val or text_val.lower() in ("none", "nan"):
            return []
        values: list[int] = []
        for part in text_val.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                values.append(int(part))
            except ValueError:
                continue
        return values
    if isinstance(raw, (list, tuple, set)):
        values = []
        for item in raw:
            values.extend(_layer_issue_codes(item))
        return values
    try:
        return [int(raw)]
    except (TypeError, ValueError):
        return []


def format_vm_layer_issues(raw: object) -> tuple[str, int | None]:
    present = set(_layer_issue_codes(raw))
    ordered = [code for code in IMAGE_LAYER_ISSUE_ORDER if code in present]
    if not ordered:
        return "—", None
    labels = [IMAGE_STATUS_MAP.get(code, f"Code {code}") for code in ordered]
    return ", ".join(labels), ordered[0]


def fetch_vms_data(
    active_db: str,
    filters: tuple[str, str, str, str],
    clusters: dict[str, str],
    hosts: dict[str, str],
    dc_id_to_name: dict[str, str],
) -> pd.DataFrame:
    """
    Выполняет SQL-запрос к ВМ с учетом выбранных фильтров.

    Args:
        active_db: Имя активной базы данных
        filters: Кортеж (dc_name, cluster_name, host_name, search_term)
        clusters: Словарь {cluster_id: cluster_name}
        hosts: Словарь {host_id: host_name}
        dc_id_to_name: Словарь {dc_id: dc_name}

    Returns:
        DataFrame с сырыми данными ВМ или пустой DF при ошибке
    """
    selected_dc_name, selected_cluster_name, selected_host_name, search_term = filters

    target_dc_id = None
    if selected_dc_name != "Все ДЦ":
        target_dc_id = next(
            (k for k, v in dc_id_to_name.items() if v == selected_dc_name), None
        )

    target_cid = None
    if selected_cluster_name != "Все кластеры":
        target_cid = next(
            (k for k, v in clusters.items() if v == selected_cluster_name), None
        )

    target_hid = None
    if selected_host_name != "Все хосты":
        target_hid = next((k for k, v in hosts.items() if v == selected_host_name), None)

    base_sql = f"""
        SELECT
            vs.vm_guid::text as vm_guid,
            vs.vm_name,
            vs.cluster_id::text as cluster_id,
            vd.status as vm_status_code,
            vd.run_on_vds::text,
            c.storage_pool_id::text as storage_pool_id,
            (
                SELECT string_agg(DISTINCT i.imagestatus::text, ',')
                FROM images i
                JOIN vm_device vd_dev ON i.image_group_id = vd_dev.device_id
                WHERE vd_dev.vm_id = vs.vm_guid
                  AND i.imagestatus IN (
                      {IMAGE_STATUS_LOCKED},
                      {IMAGE_STATUS_ILLEGAL},
                      {IMAGE_STATUS_MERGING}
                  )
            ) as layer_issue_codes
        FROM vm_static vs
        LEFT JOIN vm_dynamic vd ON vs.vm_guid = vd.vm_guid
        JOIN cluster c ON vs.cluster_id = c.cluster_id
        WHERE vs.entity_type = 'VM'
    """

    conditions = []
    sql_params = {}

    if target_dc_id:
        conditions.append("c.storage_pool_id = :dc_id")
        sql_params["dc_id"] = target_dc_id

    if target_cid:
        conditions.append("vs.cluster_id = :cluster_id")
        sql_params["cluster_id"] = target_cid

    if target_hid:
        conditions.append("vd.run_on_vds = :host_id")
        sql_params["host_id"] = target_hid

    if search_term:
        conditions.append(
            "(LOWER(vs.vm_name) LIKE LOWER(:search) OR vs.vm_guid::text LIKE LOWER(:search))"
        )
        sql_params["search"] = f"%{search_term}%"

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
    base_sql += " ORDER BY vs.vm_name"

    engine = get_sqlalchemy_engine(active_db)
    return read_sql_df(engine, text(base_sql), params=sql_params if sql_params else None)


def _resolve_health_filter(show_problems: bool, health_filter: str | None) -> str:
    if health_filter:
        return health_filter
    return "problems" if show_problems else "all"


def process_vm_dataframe(
    df: pd.DataFrame,
    clusters: dict[str, str],
    hosts: dict[str, str],
    dc_id_to_name: dict[str, str],
    show_problems: bool = False,
    health_filter: str | None = None,
) -> pd.DataFrame:
    """
    Обрабатывает сырой DataFrame: добавляет статусы, имена и фильтрует по runtime.
    Добавляет скрытые столбцы '_status_code' и '_layer_code' для подсветки в UI.
    """
    if df.empty:
        return pd.DataFrame()

    df["_status_code"] = df["vm_status_code"]
    df["status_display"] = df["vm_status_code"].apply(
        lambda x: VM_STATUS_MAP.get(x, f"Code {x}")
    )
    df["cluster_name"] = df["cluster_id"].map(clusters).fillna("Unknown Cluster")
    df["host_name"] = df["run_on_vds"].map(hosts).fillna("—")
    df["dc_name"] = df["storage_pool_id"].map(dc_id_to_name).fillna("Unknown DC")
    layer_raw = (
        df["layer_issue_codes"]
        if "layer_issue_codes" in df.columns
        else pd.Series([None] * len(df), index=df.index)
    )
    layer_pairs = [format_vm_layer_issues(raw) for raw in layer_raw]
    df["layer_display"] = [pair[0] for pair in layer_pairs]
    df["_layer_code"] = [pair[1] for pair in layer_pairs]
    df["is_problematic"] = df["vm_status_code"].map(vm_is_problem)

    kind = _resolve_health_filter(show_problems, health_filter)
    if kind == "up":
        df = df[df["vm_status_code"] == VM_STATUS_UP].copy()
    elif kind == "down":
        df = df[df["vm_status_code"] == VM_STATUS_DOWN].copy()
    elif kind == "problems":
        df = df[df["is_problematic"]].copy()

    display_df = df[
        [
            "vm_name",
            "vm_guid",
            "status_display",
            "_status_code",
            "layer_display",
            "_layer_code",
            "host_name",
            "cluster_name",
            "dc_name",
        ]
    ].copy()
    display_df.columns = [
        "Имя ВМ",
        "UUID",
        "Статус",
        "_status_code",
        "Слои",
        "_layer_code",
        "Хост",
        "Кластер",
        "Дата-центр",
    ]
    return display_df

# src/tasks/tasks_utils.py
"""
Утилиты для работы с задачами oVirt Engine.
Содержит чистые функции построения SQL-запросов и обработки DataFrame.
Не зависит от Streamlit. Тестируется изолированно.
"""

from sqlalchemy import text
import pandas as pd
from typing import Optional

from core.constants import (
    action_type_label,
    async_task_bucket_code,
    async_task_is_error,
    async_task_is_finished,
    async_task_is_running,
    async_task_result_label,
    async_task_status_label,
)


def build_audit_correlation_sql(
    host_id: Optional[str] = None,
    host_ids: Optional[list] = None,
    vm_search: Optional[str] = None,
    start_dt=None,
    end_dt=None
) -> tuple[str, dict]:
    """
    Строит SQL для поиска correlation_id в audit_log по фильтрам инфраструктуры.
    host_ids: None — без среза по хостам; [] — пустой результат; список — vds_id IN.
    """
    sql = "SELECT DISTINCT correlation_id FROM audit_log WHERE correlation_id IS NOT NULL AND deleted = false"
    params = {}

    ids = list(host_ids) if host_ids is not None else ([host_id] if host_id else None)
    if ids is not None:
        if not ids:
            sql += " AND 1=0"
        else:
            sql += " AND vds_id::text IN :h_ids"
            params["h_ids"] = tuple(ids)

    if vm_search:
        sql += " AND LOWER(vm_name) LIKE LOWER(:vm_t)"
        params["vm_t"] = f"%{vm_search}%"

    if start_dt:
        sql += " AND log_time >= :s_dt"
        params["s_dt"] = start_dt

    if end_dt:
        sql += " AND log_time <= :e_dt"
        params["e_dt"] = end_dt

    return sql, params


def build_tasks_list_sql(
    allowed_correlation_ids: Optional[list] = None,
    start_dt=None,
    end_dt=None,
    search_id: Optional[str] = None,
    limit: int = 500
) -> tuple[text, dict]:
    """
    Строит параметризованный SQL для списка async_tasks.

    Args:
        allowed_correlation_ids: Список корреляций из audit_log.
            None = фильтр не применялся.
            [] = фильтр применялся, но ничего не найдено (AND 1=0).
            [ids...] = фильтр с конкретными значениями.

    Returns:
        (sqlalchemy.text, params_dict)
    """
    sql = """
        SELECT 
            t.task_id::text, 
            t.action_type, 
            t.status, 
            t.result, 
            t.started_at, 
            t.vdsm_task_id::text as vdsm_task_id_txt, 
            t.root_command_id::text,
            COALESCE(NULLIF(c.command_type, 0), t.action_type) AS command_type
        FROM async_tasks t
        LEFT JOIN command_entities c ON t.command_id = c.command_id
        WHERE 1=1
    """
    params = {}

    if start_dt:
        sql += " AND t.started_at >= :start_dt"
        params["start_dt"] = start_dt

    if end_dt:
        sql += " AND t.started_at <= :end_dt"
        params["end_dt"] = end_dt

    if search_id:
        sql += " AND t.task_id::text LIKE :sid"
        params["sid"] = f"%{search_id}%"

    if allowed_correlation_ids is not None:
        if allowed_correlation_ids:
            sql += " AND t.root_command_id::text IN :corr_ids"
            params["corr_ids"] = tuple(allowed_correlation_ids)
        else:
            sql += " AND 1=0"

    sql += " ORDER BY t.started_at DESC LIMIT :lim"
    params["lim"] = limit

    return text(sql), params


def process_tasks_dataframe(
    df: pd.DataFrame, health_filter: str = "all"
) -> pd.DataFrame:
    """Колонки списка + pills running/finished/ошибки."""
    if df.empty:
        return pd.DataFrame()

    result = df.copy()
    command_code = result["command_type"]
    if "action_type" in result.columns:
        command_code = command_code.where(
            command_code.notna() & (command_code != 0), result["action_type"]
        )
    result["Начато"] = pd.to_datetime(result["started_at"]).dt.strftime("%d.%m.%Y %H:%M:%S")
    result["Команда"] = command_code.map(action_type_label)
    result["UUID"] = result["task_id"].astype(str)
    result["correlation"] = result["root_command_id"].astype(str)
    result["Статус"] = result["status"].map(async_task_status_label)
    result["Результат"] = result["result"].map(async_task_result_label)
    result["_vdsm_task_id"] = (
        result["vdsm_task_id_txt"].astype(str) if "vdsm_task_id_txt" in result.columns else ""
    )
    result["_status_code"] = [
        async_task_bucket_code(status, res)
        for status, res in zip(result["status"], result["result"])
    ]
    result["_result_code"] = result["result"]

    if health_filter == "running":
        mask = [
            async_task_is_running(status, res)
            for status, res in zip(result["status"], result["result"])
        ]
        result = result[mask]
    elif health_filter == "finished":
        mask = [
            async_task_is_finished(status, res)
            for status, res in zip(result["status"], result["result"])
        ]
        result = result[mask]
    elif health_filter == "errors":
        mask = [
            async_task_is_error(status, res)
            for status, res in zip(result["status"], result["result"])
        ]
        result = result[mask]

    if result.empty:
        return pd.DataFrame()

    return result[
        [
            "Начато",
            "Команда",
            "UUID",
            "correlation",
            "Статус",
            "Результат",
            "_status_code",
            "_result_code",
            "_vdsm_task_id",
        ]
    ]


def format_tasks_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Обратная совместимость: полный список без pills."""
    return process_tasks_dataframe(df, health_filter="all")


def build_task_entities_sql(task_id: str) -> tuple[str, dict]:
    sql = """
        SELECT
            e.entity_type,
            e.entity_id::text AS entity_id,
            COALESCE(
                sd.storage_name,
                vm.vm_name,
                vds.vds_name,
                bd.disk_alias
            ) AS entity_name
        FROM async_tasks_entities e
        LEFT JOIN storage_domain_static sd
            ON e.entity_id = sd.id
            AND LOWER(e.entity_type) IN ('storage', 'storage_domain')
        LEFT JOIN vm_static vm
            ON e.entity_id = vm.vm_guid
            AND LOWER(e.entity_type) = 'vm'
        LEFT JOIN vds_static vds
            ON e.entity_id = vds.vds_id
            AND LOWER(e.entity_type) IN ('vds', 'host')
        LEFT JOIN base_disks bd
            ON e.entity_id = bd.disk_id
            AND LOWER(e.entity_type) = 'disk'
        WHERE e.async_task_id::text = :tid
        ORDER BY e.entity_type, entity_name
    """
    return sql, {"tid": task_id}


def process_task_entities(entities: pd.DataFrame) -> pd.DataFrame:
    if entities is None or entities.empty:
        return pd.DataFrame(columns=["Тип", "Объект"])
    work = entities.copy()
    names = work["entity_name"] if "entity_name" in work.columns else None

    def _name(row: pd.Series) -> str:
        if names is not None:
            value = row.get("entity_name")
            if value is not None and not (isinstance(value, float) and pd.isna(value)):
                text_name = str(value).strip()
                if text_name and text_name.lower() not in ("none", "nan"):
                    return text_name
        oid = row.get("entity_id")
        text_id = "" if oid is None else str(oid).strip()
        return text_id[:8] if text_id else "—"

    work["Тип"] = work["entity_type"].fillna("—")
    work["Объект"] = work.apply(_name, axis=1)
    return work[["Тип", "Объект"]].reset_index(drop=True)

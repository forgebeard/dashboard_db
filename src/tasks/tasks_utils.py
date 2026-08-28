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


def format_tasks_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Колонки списка: Начато, Команда, Статус, Результат."""
    if df.empty:
        return pd.DataFrame()

    result = df.copy()
    command_code = result["command_type"]
    if "action_type" in result.columns:
        command_code = command_code.where(command_code.notna() & (command_code != 0), result["action_type"])
    result["Начато"] = pd.to_datetime(result["started_at"]).dt.strftime("%d.%m.%Y %H:%M:%S")
    result["Команда"] = command_code.map(action_type_label)
    result["Статус"] = result["status"].map(async_task_status_label)
    result["Результат"] = result["result"].map(async_task_result_label)
    return result[["Начато", "Команда", "Статус", "Результат"]]

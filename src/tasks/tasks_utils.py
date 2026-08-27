# src/tasks/tasks_utils.py
"""
Утилиты для работы с задачами oVirt Engine.
Содержит чистые функции построения SQL-запросов и обработки DataFrame.
Не зависит от Streamlit. Тестируется изолированно.
"""

from sqlalchemy import text
import pandas as pd
from typing import Optional


def build_audit_correlation_sql(
    host_id: Optional[str] = None,
    vm_search: Optional[str] = None,
    start_dt=None,
    end_dt=None
) -> tuple[str, dict]:
    """
    Строит SQL для поиска correlation_id в audit_log по фильтрам инфраструктуры.
    
    Returns:
        (sql_text, params_dict)
    """
    sql = "SELECT DISTINCT correlation_id FROM audit_log WHERE correlation_id IS NOT NULL AND deleted = false"
    params = {}
    
    if host_id:
        sql += " AND vds_id = :h_id"
        params["h_id"] = host_id
        
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
            c.command_type
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
        
    # Фильтр по correlation_id
    if allowed_correlation_ids is not None:
        if allowed_correlation_ids:
            sql += " AND t.root_command_id::text IN :corr_ids"
            params["corr_ids"] = tuple(allowed_correlation_ids)
        else:
            # Фильтры были заданы, но связей не найдено → пустой результат
            sql += " AND 1=0"
            
    sql += " ORDER BY t.started_at DESC LIMIT :lim"
    params["lim"] = limit
    
    return text(sql), params


def format_tasks_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Форматирует сырой DataFrame задач для отображения в UI.
    Переименовывает колонки, форматирует даты.
    
    Returns:
        Новый DataFrame с русскими заголовками. Пустой если вход пустой.
    """
    if df.empty:
        return pd.DataFrame()
        
    result = df.copy()
    result['started_at'] = pd.to_datetime(result['started_at']).dt.strftime('%d.%m.%Y %H:%M:%S')
    
    display_cols = {
        "task_id": "Task ID", 
        "action_type": "Action Code", 
        "status": "Status Code", 
        "result": "Result",
        "started_at": "Начато", 
        "vdsm_task_id_txt": "VDSM Task ID", 
        "root_command_id": "Root Cmd ID",
        "command_type": "Cmd Type"
    }
    
    return result.rename(columns=display_cols)
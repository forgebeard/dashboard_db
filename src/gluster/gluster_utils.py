# src/gluster/gluster_utils.py
"""
Утилиты для работы с данными Gluster.
Отвечает за: построение SQL-запросов к VIEW-таблицам и подготовку DataFrame для UI.
Использует только подтвержденные имена столбцов из information_schema.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd  # Работа с табличными данными и выполнение SQL-запросов
import streamlit as st  # Фреймворк UI (используется для вывода ошибок/предупреждений)
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import (
    get_sqlalchemy_engine,  # Утилита создания подключений к PostgreSQL
)
from core.ui_utils import fix_uuid_columns


def fetch_gluster_volumes(
    active_db: str, 
    filters: tuple[str, str]
) -> pd.DataFrame:
    """
    Выполняет SQL-запрос к томам Gluster через VIEW-таблицу.
    
    Args:
        active_db: Имя активной базы данных
        filters: Кортеж (cluster_name_filter, search_term)
        
    Returns:
        DataFrame с сырыми данными томов или пустой DF при ошибке
    """
    cluster_filter, search_term = filters

    # Используем gluster_volumes_view для получения cluster_name без JOIN
    base_sql = """
        SELECT 
            v.id::text AS _volume_id,
            v.vol_name,
            v.cluster_name,
            v.vol_type,
            v.status,
            v.replica_count,
            v.disperse_count,
            v.stripe_count,
            v.snapshot_count,
            vd.total_space,
            vd.used_space,
            vd.free_space
        FROM gluster_volumes_view v
        LEFT JOIN gluster_volume_details vd ON v.id::text = vd.volume_id::text
        WHERE TRUE
    """
    
    conditions = []
    sql_params = {}
    
    if cluster_filter != 'Все кластеры':
        conditions.append("v.cluster_name = :cluster")
        sql_params['cluster'] = cluster_filter
            
    if search_term:
        conditions.append(
            "(LOWER(v.vol_name) LIKE LOWER(:search) OR LOWER(v.id::text) LIKE LOWER(:search))"
        )
        sql_params['search'] = f"%{search_term}%"
        
    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
        
    base_sql += " ORDER BY v.vol_name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(base_sql), engine, params=sql_params if sql_params else None)
        return fix_uuid_columns(df)
    except Exception as e:
        st.error(f"Ошибка загрузки томов Gluster: {e}")
        return pd.DataFrame()


def process_gluster_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Обрабатывает сырой DataFrame: добавляет служебные столбцы для UI.
    
    Args:
        df: Сырой DataFrame из fetch_gluster_volumes
        
    Returns:
        Отформатированный DataFrame для отображения в таблице
    """
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    total = pd.to_numeric(df.get("total_space"), errors="coerce")
    used = pd.to_numeric(df.get("used_space"), errors="coerce")
    usage = (used / total * 100).where((total > 0) & used.notna())
    df["_usage_pct"] = usage.round(1)
    df["cluster_name"] = df["cluster_name"].fillna("—")
    df["status"] = df["status"].fillna("—")

    display_df = df[
        [
            "vol_name",
            "_volume_id",
            "cluster_name",
            "vol_type",
            "status",
            "_usage_pct",
        ]
    ].copy()
    display_df.columns = [
        "Имя тома",
        "UUID",
        "Кластер",
        "Тип",
        "Статус",
        "Заполнен (%)",
    ]
    return display_df.reset_index(drop=True)
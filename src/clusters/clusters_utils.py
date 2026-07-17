# src/clusters/clusters_utils.py
"""
Утилиты для работы с данными кластеров.
Отвечает за: построение SQL-запросов и подготовку DataFrame для отображения.
Загрузка связей инфраструктуры централизована в core.data_loader.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd          # Работа с табличными данными и выполнение SQL-запросов
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов
import streamlit as st       # Фреймворк UI (используется для вывода ошибок/предупреждений)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL


def fetch_clusters_data(
    active_db: str, 
    filters: tuple[str, str], 
    dc_id_to_name: dict[str, str]
) -> pd.DataFrame:
    """
    Выполняет SQL-запрос к кластерам с учетом выбранных фильтров.
    Агрегирует количество хостов через LEFT JOIN к view vds.
    
    Args:
        active_db: Имя активной базы данных
        filters: Кортеж (dc_name, search_term)
        dc_id_to_name: Словарь {dc_id: dc_name} из cluster_meta
        
    Returns:
        DataFrame с сырыми данными кластеров или пустой DF при ошибке
    """
    selected_dc_name, search_term = filters
    
    # Определяем ID ДЦ по имени из метаданных
    target_dc_id = None
    if selected_dc_name != 'Все ДЦ':
        target_dc_id = next((k for k, v in dc_id_to_name.items() if v == selected_dc_name), None)

    base_sql = """
        SELECT 
            c.cluster_id::text AS cluster_id,
            c.name,
            c.description,
            c.compatibility_version,
            c.storage_pool_id::text AS storage_pool_id,
            c.architecture,
            c.enable_balloon,
            c.enable_ksm,
            c.fencing_enabled,
            c.ha_reservation,
            COUNT(v.vds_id) AS host_count
        FROM cluster c
        LEFT JOIN vds v ON c.cluster_id = v.cluster_id
        WHERE TRUE
    """
    
    conditions = []
    sql_params = {}
    
    if target_dc_id:
        conditions.append("c.storage_pool_id = :dc_id")
        sql_params['dc_id'] = target_dc_id
            
    if search_term:
        conditions.append("(LOWER(c.name) LIKE LOWER(:search) OR c.cluster_id::text LIKE LOWER(:search))")
        sql_params['search'] = f"%{search_term}%"
        
    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
        
    base_sql += " GROUP BY c.cluster_id, c.name, c.description, c.compatibility_version, \
                  c.storage_pool_id, c.architecture, c.enable_balloon, c.enable_ksm, \
                  c.fencing_enabled, c.ha_reservation ORDER BY c.name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(base_sql), engine, params=sql_params if sql_params else None)
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки кластеров: {e}")
        return pd.DataFrame()


def process_cluster_dataframe(
    df: pd.DataFrame, 
    dc_id_to_name: dict[str, str], 
    show_issues: bool
) -> pd.DataFrame:
    """
    Обрабатывает сырой DataFrame: добавляет имена ДЦ, вычисляет статус кластера
    и количество замечаний. Добавляет скрытый столбец '_issue_count'.
    
    Args:
        df: Сырой DataFrame из fetch_clusters_data
        dc_id_to_name: Словарь {dc_id: dc_name}
        show_issues: Флаг фильтрации только кластеров с замечаниями
        
    Returns:
        Отформатированный DataFrame для отображения в таблице
    """
    if df.empty:
        return pd.DataFrame()

    # Обогащаем именем Дата-центра
    df['dc_name'] = df['storage_pool_id'].map(dc_id_to_name).fillna('Unknown DC')
    
    # Вычисляем количество замечаний для каждого кластера
    def count_issues(row):
        issues = 0
        if not row['fencing_enabled']: issues += 1
        if not row['enable_ksm']: issues += 1
        if not row['enable_balloon']: issues += 1
        # Примечание: точный статус хостов требует отдельного запроса,
        # здесь используем упрощенную эвристику по конфигурации
        return issues

    df['_issue_count'] = df.apply(count_issues, axis=1)
    
    # Формируем текстовый статус на основе количества проблем
    def format_status(row):
        if row['_issue_count'] == 0:
            return "OK"
        elif row['_issue_count'] <= 2:
            return f"Warning ({row['_issue_count']})"
        else:
            return f"Critical ({row['_issue_count']})"
            
    df['status_display'] = df.apply(format_status, axis=1)

    # Фильтрация по замечаниям
    if show_issues:
        df = df[df['_issue_count'] > 0].copy()

    # Формируем итоговый набор колонок для UI
    display_df = df[[
        'name', 'cluster_id', 'dc_name', 'host_count', 
        'status_display', '_issue_count'
    ]].copy()
    
    display_df.columns = [
        'Имя кластера', 'UUID', 'Дата-центр', 'Хостов', 
        'Статус', '_issue_count'
    ]
    
    return display_df
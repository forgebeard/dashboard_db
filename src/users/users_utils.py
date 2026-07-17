# src/users/users_utils.py
"""
Утилиты для работы с данными пользователей.
Отвечает за: построение SQL-запросов и подготовку DataFrame для отображения.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd          # Работа с табличными данными и выполнение SQL-запросов
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов
import streamlit as st       # Фреймворк UI (используется для вывода ошибок/предупреждений)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL


def fetch_users_data(
    active_db: str, 
    filters: tuple[str, str]
) -> pd.DataFrame:
    """
    Выполняет SQL-запрос к пользователям с учетом выбранных фильтров.
    
    Args:
        active_db: Имя активной базы данных
        filters: Кортеж (domain_name, search_term)
        
    Returns:
        DataFrame с сырыми данными пользователей или пустой DF при ошибке
    """
    selected_domain, search_term = filters

    base_sql = """
        SELECT 
            u.user_id::text AS _user_id,
            u.name,
            u.domain,
            u.namespace
        FROM users u
        WHERE TRUE
    """
    
    conditions = []
    sql_params = {}
    
    if selected_domain != 'Все домены':
        conditions.append("u.domain = :domain")
        sql_params['domain'] = selected_domain
            
    if search_term:
        conditions.append("(LOWER(u.name) LIKE LOWER(:search) OR u.user_id::text LIKE LOWER(:search))")
        sql_params['search'] = f"%{search_term}%"
        
    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
        
    base_sql += " ORDER BY u.name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(base_sql), engine, params=sql_params if sql_params else None)
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки пользователей: {e}")
        return pd.DataFrame()


def process_user_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Обрабатывает сырой DataFrame: добавляет служебные столбцы для подсветки.
    
    Args:
        df: Сырой DataFrame из fetch_users_data
        
    Returns:
        Отформатированный DataFrame для отображения в таблице
    """
    if df.empty:
        return pd.DataFrame()

    # Добавляем служебный столбец для цветовой индикации внутренних учеток
    df['_domain_type'] = df['domain'].apply(
        lambda x: 'internal' if x and 'internal' in str(x).lower() else 'external'
    )

    # Формируем итоговый набор колонок для UI
    display_df = df[[
        'name', '_user_id', 'domain', 'namespace', '_domain_type'
    ]].copy()
    
    display_df.columns = [
        'Имя', 'UUID', 'Домен', 'Namespace', '_domain_type'
    ]
    
    return display_df
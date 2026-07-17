# src/hosts/hosts_utils.py
"""
Утилиты для работы с данными Хостов.
Отвечает за: загрузку связей инфраструктуры, построение SQL-запросов 
и подготовку DataFrame для отображения.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения и путям файловой системы
import sys              # Управление путями поиска модулей (sys.path)

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd     # Работа с табличными данными и выполнение SQL-запросов
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов
import streamlit as st  # Фреймворк UI (используется для вывода ошибок/предупреждений при загрузке)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Добавляем корень src/ в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.constants import HOST_STATUS_MAP       # Глобальный справочник статусов хостов (код -> читаемое название)

def load_host_infrastructure_maps(active_db):
    """Загружает маппинги ДЦ и Кластеров для фильтрации хостов."""
    dc_to_clusters = {}
    dc_id_to_name = {}
    dc_names_set = set()
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        
        # 1. Связь Cluster -> DC (UUID)
        df_cl_dc = pd.read_sql(
            text("SELECT cluster_id::text as cid, storage_pool_id::text as spid FROM cluster"), 
            engine
        )
        for _, row in df_cl_dc.iterrows():
            dc_to_clusters.setdefault(row['spid'], []).append(row['cid'])
            
        # 2. Маппинг UUID ДЦ -> Имя ДЦ
        df_dcs = pd.read_sql(
            text("SELECT id::text as dc_id, name as dc_name FROM storage_pool"), 
            engine
        )
        for _, row in df_dcs.iterrows():
            dc_id_to_name[row['dc_id']] = row['dc_name']
            dc_names_set.add(row['dc_name'])
            
        engine.dispose()
    except Exception as e:
        st.warning(f"Не удалось загрузить связи инфраструктуры хостов: {e}")
        
    return dc_to_clusters, dc_id_to_name, dc_names_set

def fetch_hosts_data(active_db, filters, clusters, dc_id_to_name):
    """Выполняет SQL-запрос к хостам с учетом фильтров."""
    selected_dc_name, selected_cluster_name, search_term = filters
    
    target_dc_id = None
    if selected_dc_name != 'Все ДЦ':
        target_dc_id = next((k for k, v in dc_id_to_name.items() if v == selected_dc_name), None)
        
    target_cid = None
    if selected_cluster_name != 'Все кластеры':
        target_cid = next((k for k, v in clusters.items() if v == selected_cluster_name), None)

    base_sql = """
        SELECT 
            s.vds_id::text as vds_id, 
            s.vds_name, 
            s.host_name AS fqdn,
            d.status AS status_code,
            d.vm_active,
            c.cluster_id::text as cluster_id,
            c.storage_pool_id::text as storage_pool_id
        FROM vds_static s
        JOIN vds_dynamic d ON s.vds_id = d.vds_id
        LEFT JOIN cluster c ON s.cluster_id = c.cluster_id
    """
    
    conditions = []
    sql_params = {}
    
    if target_dc_id:
        conditions.append("c.storage_pool_id = :dc_id")
        sql_params['dc_id'] = target_dc_id
            
    if target_cid:
        conditions.append("s.cluster_id = :cluster_id")
        sql_params['cluster_id'] = target_cid
            
    if search_term:
        conditions.append("(LOWER(s.vds_name) LIKE LOWER(:search) OR LOWER(s.host_name) LIKE LOWER(:search))")
        sql_params['search'] = f"%{search_term}%"
        
    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)
    base_sql += " ORDER BY s.vds_name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(base_sql), engine, params=sql_params if sql_params else None)
        engine.dispose()
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки хостов: {e}")
        return pd.DataFrame()

def process_host_dataframe(df, clusters, dc_id_to_name, show_problems):
    """Обрабатывает сырой DataFrame хостов: статусы, имена, фильтрация."""
    if df.empty:
        return pd.DataFrame()

    # Используем глобальную константу
    df['status_display'] = df['status_code'].apply(
        lambda x: f"{x} ({HOST_STATUS_MAP.get(x, 'Unknown')})"
    )
    
    df['cluster_name'] = df['cluster_id'].map(clusters).fillna('Unknown Cluster')
    df['dc_name'] = df['storage_pool_id'].map(dc_id_to_name).fillna('Unknown DC')
    
    # Логика проблемных хостов: всё, кроме статуса Up (3)
    df['is_problematic'] = df['status_code'] != 3

    if show_problems:
        df = df[df['is_problematic']].copy()

    # Приводим vm_active к целому числу
    df['vm_active'] = df['vm_active'].fillna(0).astype(int)

    display_df = df[['vds_name', 'fqdn', 'vds_id', 'status_display', 'vm_active', 'cluster_name', 'dc_name']].copy()
    display_df.columns = [
        'Имя хоста', 'FQDN', 'ID', 'Статус', 'Активные ВМ', 'Кластер', 'Дата-центр'
    ]
    
    return display_df
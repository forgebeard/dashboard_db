# src/vms/vms_utils.py
"""
Утилиты для работы с данными ВМ.
Отвечает за: построение SQL-запросов и подготовку DataFrame для отображения.
Загрузка связей инфраструктуры теперь централизована в core.data_loader.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd          # Работа с табличными данными и выполнение SQL-запросов
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов
import streamlit as st       # Фреймворк UI (используется для вывода ошибок/предупреждений)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.constants import (
    VM_STATUS_DOWN,
    VM_STATUS_MAP,
    VM_STATUS_PAUSED,
    VM_STATUS_UP,
    vm_is_problem,
)


def fetch_vms_data(
    active_db: str, 
    filters: tuple[str, str, str, str], 
    clusters: dict[str, str], 
    hosts: dict[str, str], 
    dc_id_to_name: dict[str, str]
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
    
    # Определяем ID для фильтров по именам из метаданных
    target_dc_id = None
    if selected_dc_name != 'Все ДЦ':
        target_dc_id = next((k for k, v in dc_id_to_name.items() if v == selected_dc_name), None)
        
    target_cid = None
    if selected_cluster_name != 'Все кластеры':
        target_cid = next((k for k, v in clusters.items() if v == selected_cluster_name), None)
        
    target_hid = None
    if selected_host_name != 'Все хосты':
        target_hid = next((k for k, v in hosts.items() if v == selected_host_name), None)

    base_sql = """
        SELECT 
            vs.vm_guid::text as vm_guid, 
            vs.vm_name, 
            vs.cluster_id::text as cluster_id, 
            vd.status as vm_status_code, 
            vd.run_on_vds::text, 
            c.storage_pool_id::text as storage_pool_id,
            EXISTS (
                SELECT 1 FROM images i 
                JOIN vm_device vd_dev ON i.image_group_id = vd_dev.device_id 
                WHERE vd_dev.vm_id = vs.vm_guid AND i.imagestatus IN (2, 3)
            ) as has_bad_images
        FROM vm_static vs
        LEFT JOIN vm_dynamic vd ON vs.vm_guid = vd.vm_guid
        JOIN cluster c ON vs.cluster_id = c.cluster_id
        WHERE vs.entity_type = 'VM'
    """
    
    conditions = []
    sql_params = {}
    
    if target_dc_id:
        conditions.append("c.storage_pool_id = :dc_id")
        sql_params['dc_id'] = target_dc_id
            
    if target_cid:
        conditions.append("vs.cluster_id = :cluster_id")
        sql_params['cluster_id'] = target_cid
            
    if target_hid:
        conditions.append("vd.run_on_vds = :host_id")
        sql_params['host_id'] = target_hid
            
    if search_term:
        conditions.append("(LOWER(vs.vm_name) LIKE LOWER(:search) OR vs.vm_guid::text LIKE LOWER(:search))")
        sql_params['search'] = f"%{search_term}%"
        
    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
    base_sql += " ORDER BY vs.vm_name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(base_sql), engine, params=sql_params if sql_params else None)
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки ВМ: {e}")
        return pd.DataFrame()


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
    Обрабатывает сырой DataFrame: добавляет статусы, имена и фильтрует проблемы.
    Добавляет скрытый столбец '_status_code' для корректной подсветки в UI.
    """
    if df.empty:
        return pd.DataFrame()

    df['_status_code'] = df['vm_status_code']
    df['status_display'] = df['vm_status_code'].apply(
        lambda x: VM_STATUS_MAP.get(x, f"Code {x}")
    )
    df['cluster_name'] = df['cluster_id'].map(clusters).fillna('Unknown Cluster')
    df['host_name'] = df['run_on_vds'].map(hosts).fillna('—')
    df['dc_name'] = df['storage_pool_id'].map(dc_id_to_name).fillna('Unknown DC')
    bad_flags = df['has_bad_images'].fillna(False).astype(bool)
    df['is_problematic'] = [
        vm_is_problem(code, bool(bad))
        for code, bad in zip(df['vm_status_code'], bad_flags)
    ]

    kind = _resolve_health_filter(show_problems, health_filter)
    if kind == "up":
        df = df[df['vm_status_code'] == VM_STATUS_UP].copy()
    elif kind == "down":
        df = df[df['vm_status_code'] == VM_STATUS_DOWN].copy()
    elif kind == "paused":
        df = df[df['vm_status_code'] == VM_STATUS_PAUSED].copy()
    elif kind == "problems":
        df = df[df['is_problematic']].copy()

    display_df = df[[
        'vm_name', 'vm_guid', 'status_display', '_status_code', 
        'host_name', 'cluster_name', 'dc_name'
    ]].copy()
    display_df.columns = [
        'Имя ВМ', 'UUID', 'Статус', '_status_code', 
        'Хост', 'Кластер', 'Дата-центр'
    ]
    return display_df
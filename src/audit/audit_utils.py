# src/audit/audit_utils.py
"""
Утилиты для работы с журналом событий (Audit Log).
Отвечает за: загрузку связей инфраструктуры, построение SQL-запросов 
и кэшированную выборку данных аудита.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения и путям файловой системы
import sys              # Управление путями поиска модулей (sys.path)

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd     # Работа с табличными данными и выполнение SQL-запросов
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов
import streamlit as st  # Фреймворк UI (используется для кэширования @st.cache_data и вывода ошибок)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Добавляем корень src/ в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL

def load_audit_infrastructure_maps(active_db):
    """Загружает маппинги ДЦ, Кластеров, Хостов и ВМ для каскадных фильтров."""
    maps = {
        "dc_to_clusters": {},
        "cluster_to_hosts": {},
        "host_to_vms": {},
        "dc_id_to_name": {},
        "cluster_id_to_name": {},
        "host_id_to_name": {},
        "vm_id_to_name": {}
    }
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        
        # 1. DC -> Cluster & Names
        df_dc_cl = pd.read_sql(text("""
            SELECT sp.id::text as dc_id, sp.name as dc_name, 
                   c.cluster_id::text as cl_id, c.name as cl_name
            FROM storage_pool sp
            LEFT JOIN cluster c ON sp.id = c.storage_pool_id
        """), engine)
        
        for _, r in df_dc_cl.iterrows():
            # Защита от None
            dc_name = str(r['dc_name']) if r['dc_name'] else f"DC-{str(r['dc_id'])[:8]}"
            cl_name = str(r['cl_name']) if r['cl_name'] else f"Cluster-{str(r['cl_id'])[:8]}"
            
            maps["dc_id_to_name"][r['dc_id']] = dc_name
            maps["cluster_id_to_name"][r['cl_id']] = cl_name
            
            if r['cl_id']:
                maps["dc_to_clusters"].setdefault(r['dc_id'], []).append(r['cl_id'])
                
        # 2. Cluster -> Host & Names
        df_cl_host = pd.read_sql(text("""
            SELECT c.cluster_id::text as cl_id, v.vds_id::text as h_id, v.vds_name as h_name
            FROM cluster c
            LEFT JOIN vds_static v ON c.cluster_id = v.cluster_id
        """), engine)
        
        for _, r in df_cl_host.iterrows():
            # ЗАЩИТА ОТ NONE: Если имени нет, генерируем заглушку
            host_name = str(r['h_name']) if r['h_name'] else f"Host-{str(r['h_id'])[:8]}"
            
            maps["host_id_to_name"][r['h_id']] = host_name
            
            if r['h_id']:
                maps["cluster_to_hosts"].setdefault(r['cl_id'], []).append(r['h_id'])
                
        # 3. Host -> VMs (из audit_log)
        df_h_vm = pd.read_sql(text("""
            SELECT DISTINCT vds_id::text as h_id, vm_id::text as vm_id, vm_name 
            FROM audit_log 
            WHERE vds_id IS NOT NULL AND vm_id IS NOT NULL 
              AND vds_id != '00000000-0000-0000-0000-000000000000'
              AND vm_name IS NOT NULL
        """), engine)
        
        for _, r in df_h_vm.iterrows():
            vm_name = str(r['vm_name']) if r['vm_name'] else f"VM-{str(r['vm_id'])[:8]}"
            maps["vm_id_to_name"][r['vm_id']] = vm_name
            
            if r['h_id']:
                maps["host_to_vms"].setdefault(r['h_id'], set()).add(r['vm_id'])
                
        # Превращаем sets в sorted lists для UI
        for k, v in maps["host_to_vms"].items():
            maps["host_to_vms"][k] = sorted(list(v))
            
        engine.dispose()
        
    except Exception as e:
        st.warning(f"Не удалось загрузить связи для журнала: {e}")
        
    return maps

@st.cache_data(ttl=60)
def fetch_audit_logs(active_db, filters, limit_val):
    """Выполняет параметризованный запрос к audit_log."""
    
    sql = """
        SELECT 
            audit_log_id, log_time, log_type_name, severity, message,
            vds_id::text, vds_name, vm_id::text, vm_name, user_name
        FROM audit_log
        WHERE deleted = false
    """
    params = {}
    
    # Фильтр по Хосту
    if filters.get("host_id"):
        sql += " AND vds_id = :host_id"
        params["host_id"] = filters["host_id"]
        
    # Фильтр по ВМ (поиск по подстроке в имени или UUID)
    if filters.get("vm_search"):
        term = f"%{filters['vm_search']}%"
        sql += " AND (LOWER(vm_name) LIKE LOWER(:vm_term) OR vm_id::text LIKE LOWER(:vm_term))"
        params["vm_term"] = term
        
    # Фильтр по важности
    if filters.get("severity") == "errors":
        sql += " AND severity >= 3"
    elif filters.get("severity") == "warnings":
        sql += " AND severity >= 2"
        
    # Фильтры по времени
    if filters.get("start_dt"):
        sql += " AND log_time >= :start_dt"
        params["start_dt"] = filters["start_dt"]
    if filters.get("end_dt"):
        sql += " AND log_time <= :end_dt"
        params["end_dt"] = filters["end_dt"]
        
    sql += " ORDER BY log_time DESC LIMIT :lim"
    params["lim"] = limit_val
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(sql), engine, params=params)
        engine.dispose()
        
        if not df.empty:
            df['log_time'] = pd.to_datetime(df['log_time']).dt.strftime('%d.%m.%Y %H:%M:%S')
        return df
    except Exception as e:
        st.error(f"Ошибка чтения audit_log: {e}")
        return pd.DataFrame()
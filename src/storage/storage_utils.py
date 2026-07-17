# src/storage/storage_utils.py
"""
Утилиты для работы с данными хранилищ.
Отвечает за: загрузку связей инфраструктуры, построение SQL-запросов 
и подготовку DataFrame для отображения доменов хранения.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd         # Работа с табличными данными и выполнение SQL-запросов
from sqlalchemy import text # Безопасное формирование параметризованных SQL-запросов
import streamlit as st      # Фреймворк UI (используется для вывода ошибок/предупреждений при загрузке)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.constants import (
    STORAGE_DOMAIN_TYPE_MAP,  # Справочник типов доменов хранения (Data, ISO, Export...)
    STORAGE_TYPE_MAP,         # Справочник физических подключений (NFS, iSCSI, FCP...)
    SHARED_STATUS_MAP         # Справочник статусов общих доменов (Active, Maintenance...)
)

def load_storage_maps(active_db):
    """Загружает маппинги ДЦ для фильтрации."""
    dc_id_to_name = {}
    dc_names_set = set()
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        df_dcs = pd.read_sql(
            text("SELECT id::text as dc_id, name as dc_name FROM storage_pool"), 
            engine
        )
        for _, row in df_dcs.iterrows():
            dc_id_to_name[row['dc_id']] = row['dc_name']
            dc_names_set.add(row['dc_name'])
        engine.dispose()
    except Exception as e:
        st.warning(f"Не удалось загрузить связи ДЦ: {e}")
        
    return dc_id_to_name, dc_names_set

def process_storage_dataframe(df):
    """Обрабатывает сырой DataFrame доменов хранения."""
    if df.empty:
        return pd.DataFrame()

    # Маппинг статусов и типов
    df['domain_type_label'] = df['storage_domain_type'].map(STORAGE_DOMAIN_TYPE_MAP).fillna("Unknown")
    df['storage_type_label'] = df['storage_type'].map(STORAGE_TYPE_MAP).fillna("Unknown")
    df['status_label'] = df['shared_status_code'].map(SHARED_STATUS_MAP).fillna("Unknown")
    
    # Приводим к числам, заполняя NaN нулями
    total_gb = pd.to_numeric(df['available_disk_size'], errors='coerce').fillna(0)
    used_gb = pd.to_numeric(df['used_disk_size'], errors='coerce').fillna(0)
    
    # Расчет процентов. 
    # ВАЖНО: Если used > total (баг данных oVirt), ограничиваем 100% для визуализации
    raw_pct = (used_gb / total_gb * 100).where(total_gb > 0, 0)
    df['used_pct'] = raw_pct.clip(upper=100).round(1) 
    
    # Для текстового отображения можно оставить реальное значение, если нужно
    # Но для прогресс-бара лучше клипповать
    
    df['free_gb'] = (total_gb - used_gb).round(0)

    display_df = df[[
        'storage_name', 'sd_id', 'domain_type_label', 'storage_type_label', 
        'status_label', 'dc_name', 'used_pct', 'available_disk_size', 'free_gb'
    ]].copy()
    
    display_df.columns = [
        'Имя домена', 'UUID', 'Тип домена', 'Тип хранилища', 
        'Статус', 'Дата-центр', 'Заполнено (%)', 'Всего (ГБ)', 'Свободно (ГБ)'
    ]
    
    return display_df
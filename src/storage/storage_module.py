# src/storage/storage_module.py
"""
Модуль отображения списка хранилищ (UI).
Отвечает за: отрисовку фильтров, таблицы доменов и взаимодействие с инспектором.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st      # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd         # Работа с табличными данными и подготовка DataFrame для отображения
from sqlalchemy import text # Безопасное формирование параметризованных SQL-запросов

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os                   # Доступ к переменным окружения и путям файловой системы
import sys                  # Управление путями поиска модулей (sys.path)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(__file__))  # Добавляем текущую директорию в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI
from storage.storage_utils import load_storage_maps  # Загрузка связей ДЦ/Кластеры/Хосты для фильтрации хранилищ
from core.constants import (
    STORAGE_DOMAIN_TYPE_MAP,  # Справочник типов доменов хранения (Data, ISO, Export...)
    STORAGE_TYPE_MAP,         # Справочник физических подключений (NFS, iSCSI, FCP...)
    SHARED_STATUS_MAP         # Справочник статусов общих доменов (Active, Maintenance...)
)

def render_storage_list(active_db, cluster_meta):
    # --- ЗАГРУЗКА МАППИНГОВ ---
    dc_id_to_name, dc_names_set = load_storage_maps(active_db)

    # --- СТРОКА 1: ФИЛЬТРЫ ---
    col_dc, col_search = st.columns([1, 3])
    
    with col_dc:
        selected_dc_name = st.selectbox(
            "Дата-центр:", 
            ['Все ДЦ'] + sorted(list(dc_names_set)), 
            key="storage_dc_filter"
        )
        
    with col_search:
        search_term = st.text_input(
            "Поиск (Имя домена / UUID):", 
            placeholder="Введите имя...", 
            key="storage_search"
        )

    # --- ПОЛУЧЕНИЕ ДАННЫХ (ВСЯ МАТЕМАТИКА В SQL) ---
    target_dc_id = None
    if selected_dc_name != 'Все ДЦ':
        target_dc_id = next((k for k, v in dc_id_to_name.items() if v == selected_dc_name), None)

    base_sql = """
        SELECT 
            sds.id::text as sd_id,
            sds.storage_name,
            sds.storage_type,
            sds.storage_domain_type,
            -- Математика теперь здесь. COALESCE защищает от NULL.
            -- Если used > available, процент будет > 100, но мы это обработаем в UI
            ROUND(COALESCE(sdd.used_disk_size, 0)::numeric / NULLIF(COALESCE(sdd.available_disk_size, 0), 0) * 100, 1) as used_pct_raw,
            COALESCE(sdd.available_disk_size, 0) - COALESCE(sdd.used_disk_size, 0) as free_gb_raw,
            COALESCE(sdd.available_disk_size, 0) as total_gb_raw,
            
            sdss.status as shared_status_code,
            sp.name as dc_name,
            sp.id::text as pool_id
        FROM storage_domain_static sds
        JOIN storage_domain_dynamic sdd ON sds.id = sdd.id
        LEFT JOIN storage_pool_with_storage_domain spwsd ON sds.id = spwsd.storage_id
        LEFT JOIN storage_pool sp ON spwsd.storage_pool_id = sp.id
        LEFT JOIN storage_domain_shared_status sdss ON sds.id = sdss.storage_id
        WHERE 1=1
    """
    
    conditions = []
    params = {}
    
    if target_dc_id:
        conditions.append("sp.id = :dc_id")
        params['dc_id'] = target_dc_id
            
    if search_term:
        conditions.append("(LOWER(sds.storage_name) LIKE LOWER(:search) OR sds.id::text LIKE LOWER(:search))")
        params['search'] = f"%{search_term}%"
        
    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
    base_sql += " ORDER BY sds.storage_name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        raw_df = pd.read_sql(text(base_sql), engine, params=params if params else None)
        engine.dispose()
    except Exception as e:
        st.error(f"Ошибка загрузки хранилищ: {e}")
        return

    if raw_df.empty:
        st.info("Хранилища не найдены.")
        return

    # Исправляем UUID перед обработкой
    raw_df = fix_uuid_columns(raw_df)

    # --- ОБРАБОТКА ДЛЯ ОТОБРАЖЕНИЯ (ТОЛЬКО МАППИНГИ И ФОРМАТИРОВАНИЕ) ---
    raw_df['domain_type_label'] = raw_df['storage_domain_type'].map(STORAGE_DOMAIN_TYPE_MAP).fillna("Unknown")
    raw_df['storage_type_label'] = raw_df['storage_type'].map(STORAGE_TYPE_MAP).fillna("Unknown")
    raw_df['status_label'] = raw_df['shared_status_code'].map(SHARED_STATUS_MAP).fillna("Unknown")
    
    # Защита прогресс-бара: если процент > 100 или NaN, ставим 100 для визуализации
    raw_df['used_pct_display'] = raw_df['used_pct_raw'].clip(lower=0, upper=100).fillna(0)
    
    # Округляем размеры для красоты
    raw_df['total_gb_display'] = raw_df['total_gb_raw'].round(0)
    raw_df['free_gb_display'] = raw_df['free_gb_raw'].round(0)

    display_df = raw_df[[
        'storage_name', 'sd_id', 'domain_type_label', 'storage_type_label', 
        'status_label', 'dc_name', 'used_pct_display', 'total_gb_display', 'free_gb_display'
    ]].copy()
    
    display_df.columns = [
        'Имя домена', 'UUID', 'Тип домена', 'Тип хранилища', 
        'Статус', 'Дата-центр', 'Заполнено (%)', 'Всего (ГБ)', 'Свободно (ГБ)'
    ]

    # --- ОТРИСОВКА ТАБЛИЦЫ ---
    def status_color(val):
        val_str = str(val)
        if 'Problem' in val_str or '🔴' in val_str: return 'color: red; font-weight: bold'
        if 'Maintenance' in val_str: return 'color: orange'
        return ''

    styled_df = display_df.style.map(status_color, subset=['Статус'])

    column_config = {
        "Имя домена": st.column_config.TextColumn(width="medium"),
        "UUID": st.column_config.TextColumn(width="small"),
        "Заполнено (%)": st.column_config.ProgressColumn("Заполнено", min_value=0, max_value=100, format="%f%%"),
    }

    event = st.dataframe(
        styled_df,
        width='stretch', 
        hide_index=True, 
        on_select="rerun",
        selection_mode="single-row", 
        column_config=column_config, 
        height=500
    )

    # --- ИНСПЕКТОР ---
    
    if event.selection.rows:
        idx = event.selection.rows[0]
        selected_uuid = display_df.iloc[idx]['UUID']
        
        st.markdown(f"#### 🔍 Инспектор: {display_df.iloc[idx]['Имя домена']}")
        st.caption(f"UUID: `{selected_uuid}` | ДЦ: {display_df.iloc[idx]['Дата-центр']}")
        
        with st.spinner("Генерация полного отчета STORAGE-Inspector..."):
            from storage.storage_inspector_sql import get_storage_inspector_report
            result = get_storage_inspector_report(active_db, selected_uuid)
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
# src/disks/disks_diagnostics.py
"""
Модуль диагностики раздела «Диски и Образы».

Отвечает за:
- Просмотр сырых системных таблиц (images, base_disks, disk_image_dynamic) с защитой от переполнения.
- Автоматическую конвертацию UUID в читаемый формат.
- Группировку таблиц по функциональным блокам.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и SQL-запросами через SQLAlchemy
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения и путям файловой системы
import sys              # Управление путями поиска модулей (sys.path)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(__file__))  # Добавляем текущую директорию в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI
from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP  # Константы лимитов отображения строк

def render_disks_diagnostics(active_db):
    st.subheader("Таблицы раздела «Диски и Образы»")
    
    # --- КОМПАКТНЫЙ ЛИМИТ СТРОК ---
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
            <span style="font-weight: 600; font-size: 1rem; white-space: nowrap;">Лимит строк:</span>
            <div id="limit-input-container"></div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    row_limit = st.number_input(
        "Изменить лимит:", 
        label_visibility="collapsed",
        min_value=10,
        max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT,
        step=ROW_STEP,
        key=f"disks_limit_{active_db}",
        width=120
    )
    
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    disks_tables = {
        "Core Disks": {
            "base_disks": "Базовая информация о логических дисках",
            "disk_image_dynamic": "Динамические параметры образов (фактический размер)",
            "images": "Образы дисков (слои/снапшоты)"
        },
        "Mappings & Relations": {
            "image_storage_domain_map": "Привязка образов к доменам хранения",
            "disk_lun_map": "Маппинг дисков к LUN (для блочных хранилищ)",
            "vm_device": "Привязка устройств (дисков) к ВМ"
        }
    }

    try:
        raw_engine = get_sqlalchemy_engine(active_db)
        
        for group_name, tables in disks_tables.items():
            st.markdown(f"**{group_name}**")
            for table_name, description in tables.items():
                with st.expander(f"`{table_name}` — {description}", expanded=False):
                    try:
                        preview_query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {row_limit}"
                        df_table = pd.read_sql_query(preview_query, raw_engine)
                        
                        df_table = fix_uuid_columns(df_table)
                        
                        if not df_table.empty:
                            st.dataframe(df_table, width='stretch', height=400, hide_index=True)
                            st.caption(f"Показано {len(df_table)} записей из `{table_name}`")
                        else:
                            st.info(f"Таблица `{table_name}` пуста.")
                            
                    except Exception as e:
                        st.error(f"Не удалось загрузить `{table_name}`: {e}")
                    
        raw_engine.dispose()
        
    except Exception as e:
        st.error(f"Не удалось подключиться для просмотра таблиц: {e}")
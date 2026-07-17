# src/hosts/hosts_diagnostics.py
"""
Модуль диагностики раздела «Хосты».

Отвечает за:
- Просмотр сырых системных таблиц (vds_*, host_*) с лимитом строк.
- Фикс отображения UUID для корректной работы виджетов Streamlit.
- Группировку таблиц по назначению (Сеть, Оборудование, Конфигурация).
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

def render_hosts_diagnostics(active_db):
    st.subheader("Таблицы раздела «Хосты»")
    
    # --- КОМПАКТНЫЙ ЛИМИТ СТРОК (ИДЕАЛЬНО НА ОДНОЙ СТРОКЕ) ---
    # Используем CSS Flexbox для жесткого позиционирования
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
            <span style="font-weight: 600; font-size: 1rem; white-space: nowrap;">Лимит строк:</span>
            <div id="limit-input-container"></div>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    # Размещаем инпут сразу после markdown. 
    # Streamlit автоматически поместит его в поток, но мы ограничим ширину
    row_limit = st.number_input(
        "Изменить лимит:", 
        label_visibility="collapsed",
        min_value=10,
        max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT,
        step=ROW_STEP,
        key=f"host_limit_{active_db}",
        width=120  # Компактная ширина
    )
    
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    host_tables = {
        "Core": {
            "vds_static": "Статические параметры хоста",
            "vds_dynamic": "Динамический статус хоста",
            "vds_statistics": "Статистика хоста за период"
        },
        "Network": {
            "vds_interface": "Сетевые интерфейсы хоста",
            "vds_interface_statistics": "Статистика сетевых интерфейсов",
            "host_nic_vfs_config": "Конфигурация SR-IOV VFS"
        },
        "Hardware & Config": {
            "vds_kdump_status": "Статус kdump на хосте",
            "vds_spm_id_map": "Маппинг SPM",
            "host_device": "Физические устройства хоста (PCI, USB)"
        }
    }

    try:
        raw_engine = get_sqlalchemy_engine(active_db)
        
        for group_name, tables in host_tables.items():
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
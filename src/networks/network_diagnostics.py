# src/networks/network_diagnostics.py

"""
Модуль диагностики раздела «Сети».

Отвечает за:
- Просмотр сырых системных таблиц (network, vnic_profiles, mac_pools и др.) 
  с защитой от переполнения памяти.
- Автоматическую конвертацию UUID в читаемый формат.
- Группировку таблиц по функциональным блокам (Core, Physical, Config).
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и SQL-запросами через SQLAlchemy
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import sys              # Управление путями поиска модулей (sys.path)
import os               # Доступ к переменным окружения и путям файловой системы

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Добавляем корень src/ в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI
from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP  # Константы лимитов отображения строк

def render_networks_diagnostics(active_db):
    st.subheader("Таблицы раздела «Сети»")
    
    # --- ЛИМИТ СТРОК ---
    row_limit = st.number_input(
        "Лимит строк:", 
        label_visibility="collapsed",
        min_value=10,
        max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT,
        step=ROW_STEP,
        key=f"net_limit_{active_db}",
        width=120
    )
    
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    network_tables = {
        "Core": {
            "network": "Логические сети (VLAN, подсети, шлюзы)",
            "network_cluster": "Привязка сетей к кластерам и политики",
            "vnic_profiles": "Профили vNIC (QoS, фильтры)"
        },
        "Physical": {
            "network_attachments": "Подключения сетей к интерфейсам хостов/ВМ",
            "vds_interface": "Физические интерфейсы хостов (связь по имени)"
        },
        "Config": {
            "dns_resolver_configuration": "Конфигурации DNS-резолверов",
            "name_server": "Список DNS-серверов",
            "mac_pools": "Пулы MAC-адресов",
            "mac_pool_ranges": "Диапазоны MAC-адресов в пулах",
            "vfs_config_networks": "Сети в конфигурации VFS",
            "network_filter": "Фильтры трафика libvirt (nwfilter rules)"
        }
    }

    try:
        raw_engine = get_sqlalchemy_engine(active_db)
        
        for group_name, tables in network_tables.items():
            st.markdown(f" Группа: {group_name}")
            for table_name, description in tables.items():
                with st.expander(f"`{table_name}` — {description}", expanded=False):
                    try:
                        preview_query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {row_limit}"
                        df_table = pd.read_sql_query(text(preview_query), raw_engine)
                        
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
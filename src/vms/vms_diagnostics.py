# src/vms/vms_diagnostics.py
"""
Модуль диагностики раздела «Виртуальные машины».

Отвечает за:
- Просмотр сырых системных таблиц (vm_*, image_*) с защитой от переполнения памяти.
- Автоматическую конвертацию UUID в читаемый формат.
- Группировку таблиц по функциональным блокам (Core, Storage, Network, Config).
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и SQL-запросами через SQLAlchemy
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения и путям файловой системы
import sys              # Управление путями поиска модулей (sys.path)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
sys.path.append(os.path.dirname(__file__))  # Добавляем текущую директорию в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI
from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP  # Константы лимитов отображения строк


def render_vms_diagnostics(active_db: str) -> None:
    """
    Отрисовывает интерфейс диагностики таблиц ВМ с настраиваемым лимитом строк.
    
    Args:
        active_db: Имя активной базы данных для просмотра таблиц
    """
    st.subheader("Таблицы раздела «Виртуальные машины»")
    
    # Компактный селектор лимита строк
    row_limit = st.number_input(
        "Лимит строк:", 
        label_visibility="collapsed",
        min_value=10,
        max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT,
        step=ROW_STEP,
        key=f"vm_limit_{active_db}",
        width=120
    )
    
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    vm_tables = {
        "Core": {
            "vm_static": "Статические параметры ВМ",
            "vm_dynamic": "Динамический статус ВМ",
            "vm_statistics": "Статистика ВМ за период"
        },
        "Storage": {
            "vm_device": "Устройства ВМ (диски, NIC)",
            "vm_backup_disk_map": "Карта дисков для бэкапов",
            "vm_backups": "Резервные копии ВМ",
            "vm_checkpoint_disk_map": "Карта дисков для чекпоинтов",
            "vm_checkpoints": "Чекпоинты ВМ",
            "vm_ovf_generations": "Версии OVF-конфигурации"
        },
        "Network": {
            "vm_interface": "Сетевые интерфейсы ВМ",
            "vm_interface_statistics": "Статистика сетевых интерфейсов",
            "vm_interface_filter_parameters": "Параметры фильтрации трафика",
            "vm_guest_agent_interfaces": "Интерфейсы от guest agent"
        },
        "Config": {
            "vm_init": "Параметры cloud-init/sysprep",
            "vm_external_data": "Внешние метаданные ВМ",
            "vm_host_pinning_map": "Привязка ВМ к хостам",
            "vm_vds_numa_node_map": "NUMA-топология ВМ",
            "vm_pool_map": "Связь ВМ с пулами",
            "vm_pools": "Группы/пулы ВМ",
            "vm_groups": "Логические группы ВМ",
            "vm_jobs": "Специализированные задачи ВМ",
            "vm_icon_defaults": "Иконки ВМ по умолчанию",
            "vm_icons": "Пользовательские иконки ВМ",
            "vm_nvram_data": "Данные NVRAM (UEFI)"
        }
    }

    try:
        # Используем кэшированный engine без dispose() — SQLAlchemy сам управляет пулом
        engine = get_sqlalchemy_engine(active_db)
        
        for group_name, tables in vm_tables.items():
            st.markdown(f"### {group_name}")
            for table_name, description in tables.items():
                with st.expander(f"`{table_name}` — {description}", expanded=False):
                    try:
                        preview_query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {row_limit}"
                        df_table = pd.read_sql_query(text(preview_query), engine)
                        
                        df_table = fix_uuid_columns(df_table)
                        
                        if not df_table.empty:
                            st.dataframe(df_table, width='stretch', height=400, hide_index=True)
                            st.caption(f"Показано {len(df_table)} записей из `{table_name}`")
                        else:
                            st.info(f"Таблица `{table_name}` пуста.")
                            
                    except Exception as e:
                        st.error(f"Не удалось загрузить `{table_name}`: {e}")
                    
    except Exception as e:
        st.error(f"Не удалось подключиться для просмотра таблиц: {e}")
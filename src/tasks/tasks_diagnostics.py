# src/tasks/tasks_diagnostics.py
"""
Модуль диагностики раздела «Задачи».

Отвечает за:
- Просмотр сырых системных таблиц (job, step, async_tasks...) с защитой от переполнения памяти.
- Автоматическую конвертацию UUID в читаемый формат.
- Группировку таблиц по функциональным блокам (Core, Async, Relations, Audit).
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

def render_tasks_diagnostics(active_db):
    st.subheader("Таблицы раздела «Задачи»")
    
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
        key=f"task_limit_{active_db}",
        width=120
    )
    
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    task_tables = {
        "Core": {
            "job": "Родительские задачи и операции",
            "step": "Шаги выполнения операций",
            "vm_jobs": "Специфичные задачи ВМ"
        },
        "Async VDSM": {
            "async_tasks": "Асинхронные задачи VDSM",
            "command_entities": "История команд и контекст (параметры)"
        },
        "Relations": {
            "async_tasks_entities": "Привязка async-задач к сущностям",
            "job_subject_entity": "Связи задач с сущностями",
            "step_subject_entity": "Связи шагов с сущностями",
            "command_assoc_entities": "Связи команд с сущностями"
        },
        "Audit & Events": {
            "audit_log": "Аудит-лог событий",
            "event_map": "Карта событий",
            "event_notification_hist": "История уведомлений",
            "event_subscriber": "Подписчики событий",
            "dwh_history_timekeeping": "Отслеживание времени для DWH"
        }
    }

    try:
        raw_engine = get_sqlalchemy_engine(active_db)
        
        for group_name, tables in task_tables.items():
            st.markdown(f"**Группа: {group_name}**")
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
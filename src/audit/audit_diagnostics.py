# src/audit/audit_diagnostics.py
"""
Модуль диагностики раздела «Журнал событий».

Отвечает за:
- Просмотр сырых системных таблиц (audit_log, vdc_db_log) с защитой от переполнения памяти.
- Автоматическую конвертацию UUID в читаемый формат.
- Безопасный просмотр технических логов движка oVirt.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и SQL-запросами через SQLAlchemy

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения и путям файловой системы
import sys              # Управление путями поиска модулей (sys.path)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Добавляем корень src/ в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI
from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP  # Константы лимитов отображения строк

def render_audit_diagnostics(active_db):
    st.subheader("Таблицы журнала событий")
    
    row_limit = st.number_input(
        "Лимит строк:", label_visibility="collapsed",
        min_value=10, max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT, step=ROW_STEP,
        key=f"audit_diag_limit_{active_db}", width=120
    )
    
    # Список таблиц для диагностики раздела
    tables = {
        "audit_log": "Основной журнал событий (аудит действий)",
        "vdc_db_log": "Лог внутренних ошибок БД движка oVirt"
    }
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        
        for tbl, desc in tables.items():
            with st.expander(f"`{tbl}` — {desc}"):
                try:
                    # Для vdc_db_log используем специфичную колонку времени occured_at
                    if tbl == 'vdc_db_log':
                        q = f"SELECT * FROM {tbl} ORDER BY occured_at DESC LIMIT {int(row_limit)}"
                    else:
                        q = f"SELECT * FROM {tbl} ORDER BY 1 DESC LIMIT {int(row_limit)}"
                    
                    df = pd.read_sql_query(q, engine)
                    
                    # Применяем фикс для UUID колонок (если они есть)
                    df = fix_uuid_columns(df)
                    
                    if not df.empty:
                        st.dataframe(df, width='stretch', height=400, hide_index=True)
                        st.caption(f"Показано {len(df)} записей из `{tbl}`")
                    else:
                        st.info(f"Таблица `{tbl}` пуста")
                except Exception as e:
                    st.error(f"Ошибка чтения `{tbl}`: {e}")
                    
        engine.dispose()
    except Exception as e:
        st.error(f"Нет доступа к БД: {e}")
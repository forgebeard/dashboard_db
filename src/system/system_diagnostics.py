# src/system/system_diagnostics.py
"""
Модуль диагностики системных таблиц oVirt Engine.
Отвечает за: группировку таблиц и отрисовку интерфейса просмотра.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st
import pandas as pd
from sqlalchemy import text

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine
from core.ui_utils import fix_uuid_columns
from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP


def _fetch_system_table(active_db: str, table_name: str, limit: int) -> pd.DataFrame:
    """
    Локальная функция загрузки данных для диагностики.
    Изолирована от system_utils для избежания циклических импортов.
    """
    effective_limit = 50 if table_name == 'vdc_db_log' else limit
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {effective_limit}"
        df = pd.read_sql_query(text(query), engine)
        
        df = fix_uuid_columns(df)
        
        # Маскировка чувствительных данных
        sensitive_map = {
            'fence_agents': ['agent_password'],
            'providers': ['auth_password'],
            'libvirt_secrets': ['secret_value'],
            'engine_sessions': ['user_id', 'source_ip'],
        }
        
        for col in sensitive_map.get(table_name, []):
            if col in df.columns:
                df[col] = '***MASKED***'
                
        return df
        
    except Exception as e:
        st.error(f"Ошибка загрузки `{table_name}`: {e}")
        return pd.DataFrame()


def render_system_diagnostics(active_db: str) -> None:
    """
    Отрисовывает интерфейс диагностики системных таблиц.
    
    Args:
        active_db: Имя активной базы данных
    """
    st.subheader("Системные таблицы")
    
    row_limit = st.number_input(
        "Лимит строк:", 
        label_visibility="collapsed",
        min_value=10, max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT, step=ROW_STEP,
        key=f"sys_limit_{active_db}", width=120
    )
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    system_tables = {
        "Config": {
            "schema_version": "Версия схемы БД",
            "vdc_options": "Опции движка oVirt",
            "external_variable": "Внешние переменные",
        },
        "Security": {
            "engine_sessions": "Активные сессии движка",
            "fence_agents": "Агенты фенсинга (IPMI)",
            "libvirt_secrets": "Секреты libvirt",
            "certificates_data": "Данные сертификатов PKI",
        },
        "Resources & Quotas": {
            "quota": "Квоты ресурсов",
            "quota_limitation": "Ограничения квот",
            "qos": "Параметры QoS",
        },
        "Integrations": {
            "providers": "Внешние провайдеры",
            "provider_binding_host_id": "Привязка провайдеров к хостам",
            "image_transfers": "Передачи образов",
        },
        "Audit": {
            "vdc_db_log": "Лог ошибок БД",
            "business_entity_snapshot": "Снапшоты бизнес-сущностей",
            "custom_actions": "Пользовательские действия",
            "dwh_osinfo": "OS-информация для DWH",
        },
        "Internal & Utils": {
            "object_column_white_list": "Белый список колонок объектов",
            "object_column_white_list_sql": "SQL белый список колонок",
        }
    }

    try:
        for group_name, tables in system_tables.items():
            st.markdown(f"### {group_name}")
            for table_name, description in tables.items():
                with st.expander(f"`{table_name}` — {description}", expanded=False):
                    # Используем локальную функцию вместо импорта
                    df_table = _fetch_system_table(active_db, table_name, row_limit)
                    
                    if not df_table.empty:
                        diag_height = min(max(len(df_table) * 35 + 60, 200), 400)
                        
                        st.dataframe(df_table, width='stretch', height=diag_height, hide_index=True)
                        st.caption(f"Показано {len(df_table)} записей из `{table_name}`")
                    else:
                        st.info(f"Таблица `{table_name}` пуста.")
                    
    except Exception as e:
        st.error(f"Не удалось подключиться для просмотра системных таблиц: {e}")
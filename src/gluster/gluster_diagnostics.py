# src/gluster/gluster_diagnostics.py
"""
Модуль диагностики раздела «Gluster».

Отвечает за:
- Просмотр сырых системных таблиц (volumes, bricks, georep, services) с защитой от переполнения памяти.
- Автоматическую конвертацию UUID в читаемый формат.
- Группировку таблиц по функциональным блокам GlusterFS.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st          # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd             # Работа с табличными данными и SQL-запросами через SQLAlchemy
from sqlalchemy import text     # Безопасное формирование параметризованных SQL-запросов

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI
from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP  # Константы лимитов отображения строк


def render_gluster_diagnostics(active_db: str) -> None:
    """
    Отрисовывает интерфейс диагностики таблиц Gluster с настраиваемым лимитом строк.
    
    Args:
        active_db: Имя активной базы данных для просмотра таблиц
    """
    st.subheader("Таблицы раздела «Gluster»")
    
    # Компактный селектор лимита строк
    row_limit = st.number_input(
        "Лимит строк:", 
        label_visibility="collapsed",
        min_value=10,
        max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT,
        step=ROW_STEP,
        key=f"gluster_limit_{active_db}",
        width=120
    )
    
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    gluster_tables = {
        "️ Тома и Кирпичи": {
            "gluster_volumes": "Тома Gluster",
            "gluster_volume_details": "Детали томов (статистика)",
            "gluster_volume_bricks": "Кирпичи томов",
            "gluster_volume_brick_details": "Детали кирпичей",
            "gluster_volume_options": "Опции томов",
            "gluster_global_volume_options": "Глобальные опции",
            "gluster_volume_access_protocols": "Протоколы доступа",
            "gluster_volume_transport_types": "Типы транспорта",
        },
        "🔄 Geo-Replication": {
            "gluster_georep_session": "Сессии гео-репликации",
            "gluster_georep_session_details": "Детали синхронизации",
            "gluster_georep_config": "Конфигурация geo-rep",
        },
        "⚙️ Сервисы и Хуки": {
            "gluster_services": "Сервисы Gluster",
            "gluster_service_types": "Типы сервисов",
            "gluster_cluster_services": "Сервисы кластера",
            "gluster_server": "Серверы Gluster",
            "gluster_server_services": "Сервисы на серверах",
            "gluster_hooks": "Хуки кластера",
            "gluster_server_hooks": "Хуки серверов",
        },
        "📅 Планировщик и Снапшоты": {
            "gluster_volume_snapshots": "Снапшоты томов",
            "gluster_volume_snapshot_config": "Конфиг снапшотов",
            "gluster_volume_snapshot_schedules": "Расписание снапшотов",
            "gluster_scheduler_job_details": "Задачи планировщика",
            "gluster_scheduler_job_params": "Параметры задач",
        },
        "🛠️ Конфигурация": {
            "gluster_config_master": "Master конфигурация",
        }
    }

    try:
        engine = get_sqlalchemy_engine(active_db)
        
        for group_name, tables in gluster_tables.items():
            st.markdown(f"### 📂 Группа: {group_name}")
            for table_name, description in tables.items():
                with st.expander(f"`{table_name}` — {description}", expanded=False):
                    try:
                        preview_query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {row_limit}"
                        df_table = pd.read_sql_query(text(preview_query), engine)
                        
                        df_table = fix_uuid_columns(df_table)
                        
                        if not df_table.empty:
                            # 📏 ДИНАМИЧЕСКАЯ ВЫСОТА: минимум 200px, максимум 400px, +35px на строку
                            diag_height = min(max(len(df_table) * 35 + 60, 200), 400)
                            
                            st.dataframe(
                                df_table, 
                                width='stretch', 
                                height=diag_height, 
                                hide_index=True
                            )
                            st.caption(f"Показано {len(df_table)} записей из `{table_name}`")
                        else:
                            st.info(f"Таблица `{table_name}` пуста.")
                            
                    except Exception as e:
                        st.error(f"Не удалось загрузить `{table_name}`: {e}")
                    
    except Exception as e:
        st.error(f"Не удалось подключиться для просмотра таблиц: {e}")
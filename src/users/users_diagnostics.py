# src/users/users_diagnostics.py
"""
Модуль диагностики раздела «Пользователи и права».

Отвечает за:
- Просмотр сырых системных таблиц (users, roles, permissions, tags) с защитой от переполнения памяти.
- Автоматическую конвертацию UUID в читаемый формат и JSONB-полей в строки для совместимости со Streamlit.
- Группировку таблиц по функциональным блокам (Auth, RBAC, Tags, SSO).
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import json             # Сериализация JSONB-полей в строки для корректного отображения в UI

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st          # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd             # Работа с табличными данными и SQL-запросами через SQLAlchemy
from sqlalchemy import text     # Безопасное формирование параметризованных SQL-запросов

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI
from core.config import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, ROW_STEP  # Константы лимитов отображения строк


def render_users_diagnostics(active_db: str) -> None:
    """
    Отрисовывает интерфейс диагностики таблиц пользователей и прав с настраиваемым лимитом строк.
    
    Args:
        active_db: Имя активной базы данных для просмотра таблиц
    """
    st.subheader("Таблицы раздела «Пользователи и права»")
    
    # Компактный селектор лимита строк
    row_limit = st.number_input(
        "Лимит строк:", 
        label_visibility="collapsed",
        min_value=10,
        max_value=MAX_ROW_LIMIT,
        value=DEFAULT_ROW_LIMIT,
        step=ROW_STEP,
        key=f"users_limit_{active_db}",
        width=120
    )
    
    row_limit = min(int(row_limit), MAX_ROW_LIMIT) 

    users_tables = {
        "Auth & Profiles": {
            "users": "Пользователи системы",
            "user_profiles": "Свойства профилей (EAV/JSONB)",
        },
        "Roles & Permissions": {
            "roles": "Роли доступа",
            "permissions": "Назначенные права на объекты",
            "roles_groups": "Связь ролей с группами действий",
            "ad_groups": "Группы Active Directory",
        },
        "Tags & Labels": {
            "tags": "Теги объектов",
            "tags_user_map": "Теги пользователей",
            "tags_user_group_map": "Теги групп пользователей",
            "tags_vm_map": "Теги ВМ",
            "tags_vm_pool_map": "Теги пулов ВМ",
            "tags_vds_map": "Теги хостов",
            "labels": "Метки сетей/интерфейсов",
            "labels_map": "Маппинг меток",
            "vfs_config_labels": "Метки в VFS конфигурации",
        },
        "SSO & Bookmarks": {
            "sso_clients": "SSO клиенты",
            "sso_scope_dependency": "Зависимости scopes SSO",
            "bookmarks": "Закладки пользователей",
        }
    }

    try:
        # Используем кэшированный engine без dispose() — SQLAlchemy сам управляет пулом
        engine = get_sqlalchemy_engine(active_db)
        
        for group_name, tables in users_tables.items():
            st.markdown(f"### {group_name}")
            for table_name, description in tables.items():
                with st.expander(f"`{table_name}` — {description}", expanded=False):
                    try:
                        preview_query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {row_limit}"
                        df_table = pd.read_sql_query(text(preview_query), engine)
                        
                        df_table = fix_uuid_columns(df_table)
                        
                        # 🔧 FIX: Принудительная сериализация JSONB в строку для совместимости с PyArrow
                        if 'property_content' in df_table.columns:
                            df_table['property_content'] = df_table['property_content'].apply(
                                lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, (dict, list)) else str(x)
                            )
                        
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
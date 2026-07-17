# src/users/users_module.py
"""
Модуль отображения списка пользователей (UI).
Отвечает за: отрисовку фильтров, таблицы и взаимодействие с инспектором.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st
import pandas as pd

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from users.users_utils import (
    fetch_users_data,
    process_user_dataframe
)


def render_users_list(active_db: str, cluster_meta: dict) -> None:
    """
    Отрисовывает интерфейс списка пользователей с фильтрами и инспектором.
    
    Args:
        active_db: Имя активной базы данных
        cluster_meta: Закешированные метаданные инфраструктуры (не используются напрямую, но нужны для API)
    """
    # --- СТРОКА 1: ФИЛЬТРЫ ---
    col_domain, col_search = st.columns([1, 3])
    
    with col_domain:
        selected_domain = st.selectbox(
            "Домен аутентификации:", 
            ['Все домены'], 
            key="user_domain_filter"
        )
        
    with col_search:
        search_term = st.text_input(
            "Поиск (Имя / UUID):", 
            placeholder="Введите имя или UUID...", 
            key="user_search"
        )

    # --- ПОЛУЧЕНИЕ И ОБРАБОТКА ДАННЫХ ---
    filters = (selected_domain, search_term)
    raw_df = fetch_users_data(active_db, filters)
    
    if raw_df.empty:
        st.info("Пользователи не найдены.")
        return

    display_df = process_user_dataframe(raw_df)
    
    if display_df.empty:
        st.info("Нет пользователей, соответствующих критериям.")
        return

    # --- СТРОКА 2: ИТОГИ И ЭКСПОРТ ---
    col_info, col_spacer, col_btn = st.columns([2, 6, 1])
    
    with col_info:
        st.markdown(f"**Пользователей:** {len(display_df)}")
        
    with col_btn:
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Скачать CSV", 
            csv, 
            "users_list.csv", 
            "text/csv", 
            key='download-users-csv', 
            use_container_width=True
        )

    # --- ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ С ЦВЕТОВОЙ ИНДИКАЦИЕЙ ДОМЕНА ---
    
    def highlight_domain(val):
        """Подсвечивает внутренние учетки зеленым, внешние — нейтрально."""
        if not isinstance(val, str):
            return ''
        if 'internal' in val.lower():
            return 'color: #2ecc71; font-weight: bold;'
        return ''

    column_config = {
        "Имя": st.column_config.TextColumn(width="medium"),
        "UUID": st.column_config.TextColumn(width="small"),
        "Домен": st.column_config.TextColumn(width="small"),
        "Namespace": st.column_config.TextColumn(width="large"),
        "_domain_type": None  # Скрываем служебный столбец
    }

    styled_df = display_df.style.map(
        highlight_domain, 
        subset=['Домен']
    )

    #  ДИНАМИЧЕСКАЯ ВЫСОТА
    table_height = min(max(len(display_df) * 40 + 60, 200), 500)

    event = st.dataframe(
        styled_df,
        width='stretch', 
        hide_index=True, 
        on_select="rerun",
        selection_mode="single-row", 
        column_config=column_config, 
        height=table_height
    )

    # --- ИНСПЕКТОР ---
    
    if event.selection.rows:
        idx = event.selection.rows[0]
        # Используем переименованный столбец 'UUID' из display_df, а не '_user_id'
        selected_uid = display_df.iloc[idx]['UUID']
        
        # Для поиска в raw_df используем оригинальное имя '_user_id'
        row = raw_df[raw_df['_user_id'] == selected_uid].iloc[0]
        
        st.markdown(f"#### 🔍 Инспектор: {row['name']}")
        st.caption(f"UUID: `{row['_user_id']}` | Домен: {row['domain']}")
        
        with st.spinner("Генерация полного отчета User-Inspector..."):
            from users.user_inspector_sql import get_user_inspector_report
            result = get_user_inspector_report(active_db, str(row['_user_id']))
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
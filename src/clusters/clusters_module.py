# src/clusters/clusters_module.py
"""
Модуль отображения списка кластеров (UI).
Отвечает за: отрисовку фильтров, таблицы и взаимодействие с инспектором.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и подготовка DataFrame для отображения

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from clusters.clusters_utils import (
    fetch_clusters_data,            # Выполнение SQL-запроса к кластерам с учетом фильтров
    process_cluster_dataframe       # Обработка сырого DataFrame: статусы, имена, диагностика
)


def render_clusters_list(active_db: str, cluster_meta: dict) -> None:
    """
    Отрисовывает интерфейс списка кластеров с фильтрами и инспектором.
    
    Args:
        active_db: Имя активной базы данных
        cluster_meta: Закешированные метаданные инфраструктуры из session_state
    """
    # Извлекаем справочники из централизованного кэша
    dc_id_to_name = cluster_meta.get('datacenters', {})
    dc_names_set = set(dc_id_to_name.values())

    # --- СТРОКА 1: ФИЛЬТРЫ ---
    col_dc, col_search, col_diag = st.columns([1, 3, 1])
    
    with col_dc:
        selected_dc_name = st.selectbox(
            "Дата-центр:", 
            ['Все ДЦ'] + sorted(list(dc_names_set)), 
            key="cluster_dc_filter"
        )
        
    with col_search:
        search_term = st.text_input(
            "Поиск (Имя / UUID):", 
            placeholder="Введите имя или UUID...", 
            key="cluster_search"
        )

    with col_diag:
        show_issues = st.checkbox(
            "Только с замечаниями", 
            key="cluster_issue_filter", 
            help="Показать кластеры с отключенным Fencing/KSM/Balloon или проблемными хостами"
        )

    # --- ПОЛУЧЕНИЕ И ОБРАБОТКА ДАННЫХ ---
    filters = (selected_dc_name, search_term)
    raw_df = fetch_clusters_data(active_db, filters, dc_id_to_name)
    
    if raw_df.empty:
        st.info("Кластеры не найдены.")
        return

    display_df = process_cluster_dataframe(raw_df, dc_id_to_name, show_issues)
    
    if display_df.empty:
        st.info("Нет кластеров, соответствующих критериям.")
        return

    # --- СТРОКА 2: ИТОГИ И ЭКСПОРТ ---
    col_info, col_spacer, col_btn = st.columns([2, 6, 1])
    
    with col_info:
        st.markdown(f"**Кластеров:** {len(display_df)}")
        
    with col_btn:
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Скачать CSV", 
            csv, 
            "clusters_list.csv", 
            "text/csv", 
            key='download-clusters-csv', 
            use_container_width=True
        )

    # --- ТАБЛИЦА КЛАСТЕРОВ С ТОЧЕЧНОЙ ПОДСВЕТКОЙ СТАТУСА ---
    
    def highlight_status(val):
        """
        Возвращает CSS-стиль для ячейки статуса в зависимости от количества проблемных хостов.
        """
        if not isinstance(val, str):
            return ''
            
        if 'OK' in val: 
            return 'color: #2ecc71; font-weight: bold;'
        if 'Critical' in val: 
            return 'color: #e74c3c; font-weight: bold;'
        if 'Warning' in val: 
            return 'color: #f39c12; font-weight: bold;'
        return ''

    column_config = {
        "Имя кластера": st.column_config.TextColumn(width="medium"),
        "UUID": st.column_config.TextColumn(width="small"),
        "Дата-центр": st.column_config.TextColumn(width="small"),
        "Хостов": st.column_config.NumberColumn(width="small"),
        "Статус": st.column_config.TextColumn(width="small"),
        "_issue_count": None  # Скрываем служебный столбец
    }

    # Применяем стиль ТОЛЬКО к колонке 'Статус'
    styled_df = display_df.style.map(
        highlight_status, 
        subset=['Статус']
    )

    # 📏 ДИНАМИЧЕСКАЯ ВЫСОТА: минимум 200px, максимум 500px, +40px на строку
    table_height = min(max(len(display_df) * 40 + 60, 200), 500)

    event = st.dataframe(
        styled_df,
        width='stretch', 
        hide_index=True, 
        on_select="rerun",
        selection_mode="single-row", 
        column_config=column_config, 
        height=table_height  # <-- Переменная вместо жесткого значения
    )

    # --- ИНСПЕКТОР ---
    
    if event.selection.rows:
        idx = event.selection.rows[0]
        selected_uuid = display_df.iloc[idx]['UUID']
        row = raw_df[raw_df['cluster_id'] == selected_uuid].iloc[0]
        
        st.markdown(f"#### 🔍 Инспектор: {row['name']}")
        st.caption(f"UUID: `{row['cluster_id']}` | ДЦ: {row['dc_name']}")
        
        with st.spinner("Генерация полного отчета Cluster-Inspector..."):
            from clusters.cluster_inspector_sql import get_cluster_inspector_report
            result = get_cluster_inspector_report(active_db, str(row['cluster_id']))
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
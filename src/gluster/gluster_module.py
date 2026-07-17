# src/gluster/gluster_module.py
"""
Модуль отображения списка томов Gluster (UI).
Отвечает за: отрисовку фильтров, таблицы и взаимодействие с инспектором тома.
Использует только подтвержденные имена столбцов из gluster_utils.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st
import pandas as pd

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from gluster.gluster_utils import (
    fetch_gluster_volumes,
    process_gluster_dataframe
)


def render_gluster_list(active_db: str, cluster_meta: dict) -> None:
    """
    Отрисовывает интерфейс списка томов Gluster с фильтрами и инспектором.
    
    Args:
        active_db: Имя активной базы данных
        cluster_meta: Закешированные метаданные инфраструктуры (для списка кластеров)
    """
    # --- СТРОКА 1: ФИЛЬТРЫ ---
    col_cluster, col_search = st.columns([1, 3])
    
    with col_cluster:
        # Получаем список кластеров из мета-данных для фильтра
        clusters = ['Все кластеры'] + sorted(cluster_meta.get('clusters', {}).values())
        selected_cluster = st.selectbox(
            "Кластер:", 
            clusters, 
            key="gluster_cluster_filter"
        )
        
    with col_search:
        search_term = st.text_input(
            "Поиск (Имя / UUID):", 
            placeholder="Введите имя тома или UUID...", 
            key="gluster_search"
        )

    # --- ПОЛУЧЕНИЕ И ОБРАБОТКА ДАННЫХ ---
    filters = (selected_cluster, search_term)
    raw_df = fetch_gluster_volumes(active_db, filters)
    
    if raw_df.empty:
        st.info("Тома Gluster не найдены.")
        return

    display_df = process_gluster_dataframe(raw_df)
    
    if display_df.empty:
        st.info("Нет томов, соответствующих критериям.")
        return

    # --- СТРОКА 2: ИТОГИ И ЭКСПОРТ ---
    col_info, col_spacer, col_btn = st.columns([2, 6, 1])
    
    with col_info:
        st.markdown(f"**Томов:** {len(display_df)}")
        
    with col_btn:
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Скачать CSV", 
            csv, 
            "gluster_volumes.csv", 
            "text/csv", 
            key='download-gluster-csv', 
            use_container_width=True
        )

    # --- ТАБЛИЦА ТОМОВ С ЦВЕТОВОЙ ИНДИКАЦИЕЙ ---
    
    def highlight_status(val):
        """Подсвечивает статусы томов."""
        if not isinstance(val, str):
            return ''
        val_lower = val.lower()
        if 'up' in val_lower or 'online' in val_lower:
            return 'color: #2ecc71; font-weight: bold;'
        if 'down' in val_lower or 'offline' in val_lower:
            return 'color: #e74c3c; font-weight: bold;'
        if 'degraded' in val_lower or 'partial' in val_lower:
            return 'color: #f39c12; font-weight: bold;'
        return ''

    column_config = {
        "Имя тома": st.column_config.TextColumn(width="medium"),
        "UUID": st.column_config.TextColumn(width="small"),
        "Кластер": st.column_config.TextColumn(width="medium"),
        "Тип": st.column_config.TextColumn(width="small"),
        "Статус": st.column_config.TextColumn(width="small"),
        "Заполнен (%)": st.column_config.NumberColumn(format="%.1f%%", width="small"),
        "_status_type": None  # Скрываем служебный столбец
    }

    styled_df = display_df.style.map(
        highlight_status, 
        subset=['Статус']
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

    # --- ИНСПЕКТОР ТОМА ---
    
    if event.selection.rows:
        idx = event.selection.rows[0]
        selected_vid = display_df.iloc[idx]['UUID']
        row = raw_df[raw_df['_volume_id'] == selected_vid].iloc[0]
        
        st.markdown(f"#### 🔍 Инспектор тома: {row['vol_name']}")
        st.caption(f"UUID: `{row['_volume_id']}` | Кластер: {row['cluster_name']}")
        
        with st.spinner("Генерация полного отчета Volume-Inspector..."):
            from gluster.gluster_inspector_sql import get_gluster_volume_report
            result = get_gluster_volume_report(active_db, str(row['_volume_id']))
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
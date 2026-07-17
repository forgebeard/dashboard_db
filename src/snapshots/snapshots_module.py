# src/snapshots/snapshots_module.py
"""
Модуль отображения списка снапшотов (UI).
Отвечает за: отрисовку фильтров, таблицы и взаимодействие с инспектором.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и подготовка DataFrame для отображения

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from snapshots.snapshots_utils import (
    fetch_snapshots_data,            # Выполнение SQL-запроса к снапшотам с учетом фильтров
    process_snapshot_dataframe       # Обработка сырого DataFrame: статусы, имена, фильтрация
)


def render_snapshots_list(active_db: str, cluster_meta: dict) -> None:
    """
    Отрисовывает интерфейс списка снапшотов с фильтрами и инспектором.
    
    Args:
        active_db: Имя активной базы данных
        cluster_meta: Закешированные метаданные инфраструктуры из session_state
    """
    # Извлекаем справочники из централизованного кэша
    clusters = {str(k): v for k, v in cluster_meta.get('clusters', {}).items()}
    dc_id_to_name = cluster_meta.get('datacenters', {})
    dc_names_set = set(dc_id_to_name.values())

    # --- СТРОКА 1: ФИЛЬТРЫ ---
    col_dc, col_cl, col_search, col_status = st.columns([1, 1, 3, 1])
    
    with col_dc:
        selected_dc_name = st.selectbox(
            "Дата-центр:", 
            ['Все ДЦ'] + sorted(list(dc_names_set)), 
            key="snap_dc_filter"
        )
        
    with col_cl:
        cl_options = ['Все кластеры']
        target_dc_id = None
        
        if selected_dc_name != 'Все ДЦ':
            target_dc_id = next((k for k, v in dc_id_to_name.items() if v == selected_dc_name), None)
            if target_dc_id and target_dc_id in cluster_meta.get('dc_to_clusters', {}):
                valid_cids = cluster_meta['dc_to_clusters'][target_dc_id]
                valid_names = [clusters.get(cid, f"Cluster-{cid[:8]}") for cid in valid_cids]
                cl_options += sorted(valid_names)
            else:
                cl_options += sorted(set(clusters.values()))
        else:
            cl_options += sorted(set(clusters.values()))
            
        selected_cluster_name = st.selectbox("Кластер:", cl_options, key="snap_cluster_filter")

    with col_search:
        search_term = st.text_input(
            "Поиск (Имя ВМ / UUID снапшота):", 
            placeholder="Введите имя или UUID...", 
            key="snap_search"
        )

    with col_status:
        status_options = ['Все статусы', 'OK', 'LOCKED', 'ILLEGAL', 'MERGING', 'UNASSIGNED', 'UPLOADING']
        selected_status = st.selectbox("Статус образа:", status_options, key="snap_status_filter")

    # --- ПОЛУЧЕНИЕ И ОБРАБОТКА ДАННЫХ ---
    filters = (selected_dc_name, selected_cluster_name, search_term, selected_status)
    raw_df = fetch_snapshots_data(active_db, filters, dc_id_to_name, clusters)
    
    if raw_df.empty:
        st.info("Снапшоты не найдены.")
        return

    display_df = process_snapshot_dataframe(raw_df, dc_id_to_name, clusters)
    
    if display_df.empty:
        st.info("Нет снапшотов, соответствующих критериям.")
        return

    # --- СТРОКА 2: ИТОГИ И ЭКСПОРТ ---
    col_info, col_spacer, col_btn = st.columns([2, 6, 1])
    
    with col_info:
        st.markdown(f"**Снапшотов:** {len(display_df)}")
        
    with col_btn:
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Скачать CSV", 
            csv, 
            "snapshots_list.csv", 
            "text/csv", 
            key='download-snapshots-csv', 
            use_container_width=True
        )

    # --- ТАБЛИЦА СНАПШОТОВ С ТОЧЕЧНОЙ ПОДСВЕТКОЙ СТАТУСА ---
    
    def highlight_image_status(val):
        """Возвращает CSS-стиль для ячейки статуса образа."""
        if not isinstance(val, str):
            return ''
            
        if val == 'OK': 
            return 'color: #2ecc71; font-weight: bold;'
        if val == 'LOCKED': 
            return 'color: #e74c3c; font-weight: bold;'
        if val == 'ILLEGAL': 
            return 'color: #f39c12; font-weight: bold;'
        return ''

    column_config = {
        "Имя ВМ": st.column_config.TextColumn(width="medium"),
        "UUID снапшота": st.column_config.TextColumn(width="small"),
        "Дата создания": st.column_config.DatetimeColumn(format="DD.MM.YYYY HH:mm", width="medium"),
        "Тип": st.column_config.TextColumn(width="small"),
        "Размер": st.column_config.NumberColumn(format="%.2f ГБ", width="small"),
        "Статус образа": st.column_config.TextColumn(width="small"),
        "Хранилище": st.column_config.TextColumn(width="small"),
        "_image_status_code": None  # Скрываем служебный столбец
    }

    # Применяем стиль ТОЛЬКО к колонке 'Статус образа'
    styled_df = display_df.style.map(
        highlight_image_status, 
        subset=['Статус образа']
    )

    #  ДИНАМИЧЕСКАЯ ВЫСОТА: минимум 200px, максимум 500px, +40px на строку
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
        selected_vm_id = display_df.iloc[idx]['_vm_id']
        row = raw_df[raw_df['_vm_id'] == selected_vm_id].iloc[0]
        
        # Используем оригинальные имена столбцов из raw_df, а не переименованные из display_df
        st.markdown(f"#### 🔍 Инспектор: {row['vm_name']}")
        st.caption(f"ВМ UUID: `{row['_vm_id']}` | Снапшот: {row['snapshot_id']}")
        
        with st.spinner("Генерация полного отчета Snapshot-Inspector..."):
            from snapshots.snapshot_inspector_sql import get_snapshot_inspector_report
            result = get_snapshot_inspector_report(active_db, str(row['_vm_id']))
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
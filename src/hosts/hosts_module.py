# src/hosts/hosts_module.py
"""
Модуль отображения списка хостов oVirt Engine (UI).
Отвечает за: отрисовку фильтров, таблицы и взаимодействие с инспектором.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и подготовка DataFrame для отображения

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from hosts.hosts_utils import (
    load_host_infrastructure_maps,  # Загрузка связей ДЦ/Кластеры для каскадных фильтров хостов
    fetch_hosts_data,               # Выполнение SQL-запроса к хостам с учетом выбранных фильтров
    process_host_dataframe          # Обработка сырого DataFrame: статусы, имена, фильтрация проблемных
)

def render_hosts_list(active_db, cluster_meta):
    clusters_raw = cluster_meta.get('clusters', {})
    
    # Приводим ключи к строкам для надежности
    clusters = {str(k): v for k, v in clusters_raw.items()}
    
    # --- ЗАГРУЗКА ДОПОЛНИТЕЛЬНЫХ СВЯЗЕЙ ИЗ БД ---
    dc_to_clusters, dc_id_to_name, dc_names_set = load_host_infrastructure_maps(active_db)

    # --- СТРОКА 1: ФИЛЬТРЫ ---
    col_dc, col_cl, col_search, col_prob = st.columns([1, 1, 2, 1])
    
    with col_dc:
        selected_dc_name = st.selectbox(
            "Дата-центр:", 
            ['Все ДЦ'] + sorted(list(dc_names_set)), 
            key="host_dc_filter"
        )
        
    with col_cl:
        cl_options = ['Все кластеры']
        target_dc_id = None
        
        if selected_dc_name != 'Все ДЦ':
            target_dc_id = next((k for k, v in dc_id_to_name.items() if v == selected_dc_name), None)
            
            if target_dc_id and target_dc_id in dc_to_clusters:
                valid_cids = dc_to_clusters[target_dc_id]
                valid_names = [clusters.get(cid, f"Cluster-{cid[:8]}") for cid in valid_cids]
                cl_options += sorted(valid_names)
            else:
                cl_options += sorted(set(clusters.values()))
        else:
            cl_options += sorted(set(clusters.values()))
            
        selected_cluster_name = st.selectbox("Кластер:", cl_options, key="host_cluster_filter")

    with col_search:
        search_term = st.text_input(
            "Поиск (Имя / FQDN):", 
            placeholder="Введите имя хоста или FQDN...", 
            key="host_search"
        )

    with col_prob:
        show_problems = st.checkbox(
            "Только проблемные", 
            key="host_prob_filter", 
            help="Скрыть стабильные Up/Maintenance"
        )

    # --- ПОЛУЧЕНИЕ И ОБРАБОТКА ДАННЫХ ---
    filters = (selected_dc_name, selected_cluster_name, search_term)
    raw_df = fetch_hosts_data(active_db, filters, clusters, dc_id_to_name)
    
    if raw_df.empty:
        st.info("Хосты не найдены.")
        return

    display_df = process_host_dataframe(raw_df, clusters, dc_id_to_name, show_problems)
    
    if display_df.empty:
        st.info("Нет хостов, соответствующих критериям (например, только проблемные).")
        return

    # --- СТРОКА 2: ИТОГИ И ЭКСПОРТ ---
    col_info, col_spacer, col_btn = st.columns([2, 6, 1])
    
    with col_info:
        st.markdown(f"**Хостов:** {len(display_df)}")
        
    with col_btn:
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Скачать CSV", csv, "hosts_list.csv", "text/csv", key='download-hosts-csv', use_container_width=True)

    # --- ТАБЛИЦА ХОСТОВ ---
    def status_color(val):
        val_str = str(val)
        if '▶️ Up' in val_str: return 'color: green; font-weight: bold'
        if '⏹️ Down' in val_str: return 'color: gray'
        if any(x in val_str for x in ['Error', 'NonResponsive', 'NonOperational', 'InstallFailed', 'Kdumping']): 
            return 'color: red; font-weight: bold'
        if 'Maintenance' in val_str or 'Reboot' in val_str: return 'color: orange'
        return ''

    styled_df = display_df.style.map(status_color, subset=['Статус'])

    column_config = {
        "Имя хоста": st.column_config.TextColumn(width="small"),
        "FQDN": st.column_config.TextColumn(width="small"),
        "ID": st.column_config.TextColumn(width="medium"),
        "Статус": st.column_config.TextColumn(width="small"),
        "Активные ВМ": st.column_config.NumberColumn(width="small"),
        "Кластер": st.column_config.TextColumn(width="small"),
        "Дата-центр": st.column_config.TextColumn(width="small"),
    }

    event = st.dataframe(
        styled_df, 
        width='stretch', 
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config=column_config,
        height=500
    )

    # --- ИНСПЕКТОР ---
    
    if event.selection.rows:
        idx = event.selection.rows[0]
        selected_id = display_df.iloc[idx]['ID']
        # Ищем исходные данные по ID для передачи в инспектор
        row = raw_df[raw_df['vds_id'] == selected_id].iloc[0]
        
        st.markdown(f"#### 🔍 Инспектор хоста: {row['vds_name']}")
        st.caption(f"ID: `{row['vds_id']}` | FQDN: {row['fqdn']} | Кластер: {row['cluster_name']} | ДЦ: {row['dc_name']}")
        
        with st.spinner("Генерация полного отчета Host-Inspector..."):
            from hosts.host_inspector_sql import get_host_inspector_report
            result = get_host_inspector_report(active_db, str(row['vds_id']))
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
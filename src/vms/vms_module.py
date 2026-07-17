# src/vms/vms_module.py
"""
Модуль отображения списка виртуальных машин (UI).
Отвечает за: отрисовку фильтров, таблицы и взаимодействие с инспектором.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd     # Работа с табличными данными и подготовка DataFrame для отображения

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from vms.vms_utils import (
    fetch_vms_data,            # Выполнение SQL-запроса к ВМ с учетом выбранных фильтров
    process_vm_dataframe       # Обработка сырого DataFrame: статусы, имена, фильтрация проблемных
)
from core.constants import VM_STATUS_MAP  # Глобальный справочник статусов для подсветки


def render_vms_list(active_db: str, cluster_meta: dict) -> None:
    """
    Отрисовывает интерфейс списка ВМ с каскадными фильтрами и инспектором.
    
    Args:
        active_db: Имя активной базы данных
        cluster_meta: Закешированные метаданные инфраструктуры из session_state
    """
    # Извлекаем связи из централизованного кэша метаданных
    clusters = {str(k): v for k, v in cluster_meta.get('clusters', {}).items()}
    hosts = {str(k): v for k, v in cluster_meta.get('hosts', {}).items()}
    dc_to_clusters = cluster_meta.get('dc_to_clusters', {})
    cluster_to_hosts = cluster_meta.get('cluster_to_hosts', {})
    dc_id_to_name = cluster_meta.get('datacenters', {})
    dc_names_set = set(dc_id_to_name.values())

    # --- СТРОКА 1: КАСКАДНЫЕ ФИЛЬТРЫ ---
    col_dc, col_cl, col_host, col_search, col_prob = st.columns([1, 1, 1, 2, 1])
    
    with col_dc:
        selected_dc_name = st.selectbox(
            "Дата-центр:", 
            ['Все ДЦ'] + sorted(list(dc_names_set)), 
            key="vm_dc_filter"
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
            
        selected_cluster_name = st.selectbox("Кластер:", cl_options, key="vm_cluster_filter")

    with col_host:
        h_options = ['Все хосты']
        target_cid = None
        
        if selected_cluster_name != 'Все кластеры':
            target_cid = next((k for k, v in clusters.items() if v == selected_cluster_name), None)
            if target_cid and target_cid in cluster_to_hosts:
                valid_vids = cluster_to_hosts[target_cid]
                valid_names = [hosts.get(vid, f"Host-{vid[:8]}") for vid in valid_vids]
                h_options += sorted(valid_names)
            else:
                h_options += sorted(set(hosts.values()))
        else:
            h_options += sorted(set(hosts.values()))
            
        selected_host_name = st.selectbox("Хост:", h_options, key="vm_host_filter")

    with col_search:
        search_term = st.text_input(
            "Поиск (Имя / UUID):", 
            placeholder="Введите имя или UUID...", 
            key="vm_search"
        )

    with col_prob:
        show_problems = st.checkbox(
            "Только проблемные", 
            key="vm_prob_filter", 
            help="Скрыть стабильные Up/Down"
        )

    # --- ПОЛУЧЕНИЕ И ОБРАБОТКА ДАННЫХ ---
    filters = (selected_dc_name, selected_cluster_name, selected_host_name, search_term)
    raw_df = fetch_vms_data(active_db, filters, clusters, hosts, dc_id_to_name)
    
    if raw_df.empty:
        st.info("ВМ не найдены.")
        return

    display_df = process_vm_dataframe(raw_df, clusters, hosts, dc_id_to_name, show_problems)
    
    if display_df.empty:
        st.info("Нет ВМ, соответствующих критериям (например, только проблемные).")
        return

    # --- СТРОКА 2: ИТОГИ И ЭКСПОРТ ---
    col_info, col_spacer, col_btn = st.columns([2, 6, 1])
    
    with col_info:
        st.markdown(f"**Виртуальных машин:** {len(display_df)}")
        
    with col_btn:
        csv = display_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Скачать CSV", 
            csv, 
            "vms_list.csv", 
            "text/csv", 
            key='download-csv', 
            use_container_width=True
        )

    # --- ТАБЛИЦА ВМ С ТОЧЕЧНОЙ ПОДСВЕТКОЙ СТАТУСА ---
    
    def highlight_status(val):
        """
        Возвращает CSS-стиль для ячейки статуса в зависимости от её текстового значения.
        Работает через subset, поэтому val — это просто строка статуса.
        """
        if not isinstance(val, str):
            return ''
            
        # Проверяем по тексту, так как в subset передается уже отформатированное значение
        if 'Up' in val: 
            return 'color: #2ecc71; font-weight: bold;'  # Зеленый
        if 'Down' in val: 
            return 'color: #95a5a6;'                     # Серый
        if any(x in val for x in ['Locked', 'Illegal', 'NotResponding', 'PoweringDown']): 
            return 'color: #e67e22; font-weight: bold;'  # Оранжевый
        return ''

    column_config = {
        "Имя ВМ": st.column_config.TextColumn(width="small"),
        "UUID": st.column_config.TextColumn(width="small"),
        "Статус": st.column_config.TextColumn(width="small"),
        "Хост": st.column_config.TextColumn(width="small"),
        "Кластер": st.column_config.TextColumn(width="small"),
        "Дата-центр": st.column_config.TextColumn(width="small"),
        "_status_code": None  # Скрываем служебный столбец
    }

    # Применяем стиль ТОЛЬКО к колонке 'Статус'
    styled_df = display_df.style.map(
        highlight_status, 
        subset=['Статус']
    )

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
        selected_uuid = display_df.iloc[idx]['UUID']
        row = raw_df[raw_df['vm_guid'] == selected_uuid].iloc[0]
        
        st.markdown(f"#### 🔍 Инспектор: {row['vm_name']}")
        st.caption(f"UUID: `{row['vm_guid']}` | Статус: {row['status_display']}")
        
        with st.spinner("Генерация полного отчета VM-Inspector..."):
            from vms.vm_inspector_sql import get_vm_inspector_report
            result = get_vm_inspector_report(active_db, str(row['vm_guid']))
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
# src/networks/network_module.py
"""
Модуль отображения списка логических сетей (UI).
Отвечает за: отрисовку фильтров (по ДЦ/VLAN), таблицы сетей и взаимодействие 
с инспектором для глубокого анализа конкретной сети.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st      # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd         # Работа с табличными данными и подготовка DataFrame для отображения
from sqlalchemy import text # Безопасное формирование параметризованных SQL-запросов

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os                   # Доступ к переменным окружения и путям файловой системы
import sys                  # Управление путями поиска модулей (sys.path)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Добавляем корень src/ в путь поиска
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.ui_utils import fix_uuid_columns       # Функция конвертации UUID-объектов в строки для UI

def render_networks_list(active_db, cluster_meta):
    
    # Загружаем имена Дата-центров (Storage Pools) напрямую
    dc_map = {}
    try:
        engine = get_sqlalchemy_engine(active_db)
        df_dcs = pd.read_sql("SELECT id::text, name FROM storage_pool", engine)
        engine.dispose()
        dc_map = dict(zip(df_dcs['id'], df_dcs['name']))
    except Exception as e:
        st.warning(f"Не удалось загрузить список ДЦ: {e}")

    # --- ФИЛЬТРЫ ---
    col_dc, col_search = st.columns([1, 2])
    
    with col_dc:
        selected_dc = st.selectbox(
            "Дата-центр:", 
            ['Все ДЦ'] + sorted(set(dc_map.values())),
            key="net_dc_filter"
        )
        
    with col_search:
        search_term = st.text_input("Поиск (Имя / VLAN / UUID):", placeholder="Введите имя, VLAN или UUID...", key="net_search")

    base_sql = """
        SELECT 
            n.id, n.name, n.description, n.vlan_id, n.vm_network, 
            n.storage_pool_id, n.mtu, n.stp, n.label
        FROM network n
    """
    
    conditions = []
    sql_params = {}
    
    if selected_dc != 'Все ДЦ':
        dc_id = next((k for k, v in dc_map.items() if v == selected_dc), None)
        if dc_id:
            conditions.append("n.storage_pool_id = :dc_id")
            sql_params['dc_id'] = dc_id
            
    if search_term:
        conditions.append("(LOWER(n.name) LIKE LOWER(:search) OR n.vlan_id::text LIKE LOWER(:search) OR n.id::text LIKE LOWER(:search))")
        sql_params['search'] = f"%{search_term}%"
        
    if conditions:
        base_sql += " WHERE " + " AND ".join(conditions)
    base_sql += " ORDER BY n.name"

    try:
        engine = get_sqlalchemy_engine(active_db)
        # Используем text() для безопасности и передачи параметров
        query = text(base_sql)
        df = pd.read_sql(query, engine, params=sql_params if sql_params else None)
        engine.dispose()
    except Exception as e:
        st.error(f"Ошибка загрузки сетей: {e}")
        return

    if df.empty:
        st.info("Сети не найдены.")
        return

    df = fix_uuid_columns(df)

    # Маппинг имен ДЦ
    df['dc_name'] = df['storage_pool_id'].map(dc_map).fillna('Unknown DC')
    df['vlan_display'] = df['vlan_id'].apply(lambda x: f"VLAN {x}" if x is not None else "No VLAN")
    
    display_df = df[['name', 'id', 'vlan_display', 'vm_network', 'mtu', 'dc_name']].copy()
    display_df.columns = ['Имя сети', 'UUID', 'VLAN', 'VM Network', 'MTU', 'Дата-центр']
    
    column_config = {
        "Имя сети": st.column_config.TextColumn(width="small"),
        "UUID": st.column_config.TextColumn(width="small"),
        "VLAN": st.column_config.TextColumn(width="small"),
        "VM Network": st.column_config.CheckboxColumn(width="small"),
        "MTU": st.column_config.NumberColumn(width="small"),
        "Дата-центр": st.column_config.TextColumn(width="small")
    }

    event = st.dataframe(
        display_df, width='stretch', hide_index=True, on_select="rerun",
        selection_mode="single-row", column_config=column_config, height=500
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        row = df.iloc[idx]
        st.divider()
        st.markdown(f"#### 🔍 Инспектор сети: {row['name']}")
        st.caption(f"UUID: `{row['id']}` | ДЦ: {row['dc_name']} | VLAN: {row['vlan_display']}")
        
        with st.spinner("Генерация отчета Network-Inspector..."):
            from networks.network_inspector_sql import get_network_inspector_report
            report_text = get_network_inspector_report(active_db, str(row['id']))
        st.code(report_text, language="text")
    
    # Вызов блока диагностики (сырые таблицы)
    from networks.network_diagnostics import render_networks_diagnostics
    render_networks_diagnostics(active_db)
# src/tasks/tasks_module.py
"""
Модуль отображения списка задач VDSM (UI).
Отвечает за: отрисовку фильтров (по ДЦ/Хосту/ВМ), таблицы асинхронных задач 
и взаимодействие с инспектором для детального анализа конкретной операции.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st      # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd         # Работа с табличными данными и подготовка DataFrame для отображения
from sqlalchemy import text # Безопасное формирование параметризованных SQL-запросов
from datetime import datetime  # Форматирование имен файлов при экспорте CSV

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from .task_inspector_sql import get_task_inspector_report  # Генерация текстового отчета по выбранной задаче
from core.db_utils import get_sqlalchemy_engine                 # Утилита создания подключений к PostgreSQL
from audit.audit_utils import load_audit_infrastructure_maps  # Загрузка связей инфраструктуры для каскадных фильтров

def render_tasks_list(active_db):
    
    # Загружаем карты инфраструктуры для фильтров
    maps = load_audit_infrastructure_maps(active_db)
    
    # --- СТРОКА 1: ФИЛЬТРЫ ИНФРАСТРУКТУРЫ ---
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    
    with c1:
        dc_opts = ['Все ДЦ'] + sorted(set(maps["dc_id_to_name"].values()))
        sel_dc = st.selectbox("Дата-центр", dc_opts, key="task_dc")
        
    with c2:
        cl_opts = ['Все кластеры']
        if sel_dc != 'Все ДЦ':
            dc_id = next((k for k,v in maps["dc_id_to_name"].items() if v == sel_dc), None)
            valid_cls = [maps["cluster_id_to_name"][cid] for cid in maps["dc_to_clusters"].get(dc_id, []) if cid in maps["cluster_id_to_name"]]
            cl_opts += sorted(valid_cls)
        else:
            cl_opts += sorted(set(maps["cluster_id_to_name"].values()))
        sel_cl = st.selectbox("Кластер", cl_opts, key="task_cl")
        
    with c3:
        h_opts = ['Все хосты']
        if sel_cl != 'Все кластеры':
            cl_id = next((k for k,v in maps["cluster_id_to_name"].items() if v == sel_cl), None)
            valid_hosts = [maps["host_id_to_name"][hid] for hid in maps["cluster_to_hosts"].get(cl_id, []) if hid in maps["host_id_to_name"]]
            h_opts += sorted(valid_hosts)
        else:
            h_opts += sorted(set(maps["host_id_to_name"].values()))
        sel_host = st.selectbox("Хост", h_opts, key="task_host")

    with c4:
        search_vm = st.text_input("Поиск ВМ (имя)", placeholder="Например: zabbix...", key="task_vm_search")

    # --- СТРОКА 2: ВРЕМЯ И ТЕХНИЧЕСКИЙ ПОИСК ---
    t1, t2, t3 = st.columns([2, 2, 2])
    with t1: start_dt = st.datetime_input("С даты", value=None, key="task_start")
    with t2: end_dt = st.datetime_input("По дату", value=None, key="task_end")
    with t3: search_id = st.text_input("Поиск по Task ID", placeholder="UUID задачи...", key="task_id_search")

    # --- ЛОГИКА КОСВЕННОЙ ФИЛЬТРАЦИИ ЧЕРЕЗ AUDIT_LOG ---
    allowed_correlation_ids = None
    
    # Если выбран Хост или ВМ, пытаемся найти связанные correlation_id
    host_id = next((k for k,v in maps["host_id_to_name"].items() if v == sel_host), None)
    
    if host_id or search_vm:
        audit_sql = "SELECT DISTINCT correlation_id FROM audit_log WHERE correlation_id IS NOT NULL AND deleted = false"
        audit_params = {}
        
        if host_id:
            audit_sql += " AND vds_id = :h_id"
            audit_params["h_id"] = host_id
            
        if search_vm:
            audit_sql += " AND LOWER(vm_name) LIKE LOWER(:vm_t)"
            audit_params["vm_t"] = f"%{search_vm}%"
            
        if start_dt:
            audit_sql += " AND log_time >= :s_dt"
            audit_params["s_dt"] = start_dt
        if end_dt:
            audit_sql += " AND log_time <= :e_dt"
            audit_params["e_dt"] = end_dt
            
        try:
            engine_temp = get_sqlalchemy_engine(active_db)
            df_corr = pd.read_sql(text(audit_sql), engine_temp, params=audit_params)
            engine_temp.dispose()
            if not df_corr.empty:
                allowed_correlation_ids = df_corr['correlation_id'].tolist()
        except Exception:
            pass # Если не удалось связать, показываем все задачи

    # --- ОСНОВНОЙ ЗАПРОС К ASYNC_TASKS ---
    sql = """
        SELECT 
            t.task_id::text, 
            t.action_type, 
            t.status, 
            t.result, 
            t.started_at, 
            t.vdsm_task_id::text as vdsm_task_id_txt, 
            t.root_command_id::text,
            c.command_type
        FROM async_tasks t
        LEFT JOIN command_entities c ON t.command_id = c.command_id
        WHERE 1=1
    """
    params = {}
    
    if start_dt:
        sql += " AND t.started_at >= :start_dt"
        params["start_dt"] = start_dt
    if end_dt:
        sql += " AND t.started_at <= :end_dt"
        params["end_dt"] = end_dt
    if search_id:
        sql += " AND t.task_id::text LIKE :sid"
        params["sid"] = f"%{search_id}%"
        
    # Применяем фильтр по correlation_id, если он был найден
    if allowed_correlation_ids is not None:
        if allowed_correlation_ids:
            sql += " AND t.root_command_id::text IN :corr_ids"
            params["corr_ids"] = tuple(allowed_correlation_ids)
        else:
            # Если фильтры были заданы, но связей не найдено - показываем пустоту
            sql += " AND 1=0" 
            
    sql += " ORDER BY t.started_at DESC LIMIT 500"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(sql), engine, params=params)
        engine.dispose()
        
        if df.empty:
            st.info("Задач не найдено по заданным критериям.")
            return
            
        # Форматирование времени
        if not df.empty:
            df['started_at'] = pd.to_datetime(df['started_at']).dt.strftime('%d.%m.%Y %H:%M:%S')
            
        # --- ТАБЛИЦА ---
        display_cols = {
            "task_id": "Task ID", 
            "action_type": "Action Code", 
            "status": "Status Code", 
            "result": "Result",
            "started_at": "Начато", 
            "vdsm_task_id_txt": "VDSM Task ID", 
            "root_command_id": "Root Cmd ID",
            "command_type": "Cmd Type"
        }
        
        show_df = df.rename(columns=display_cols)
        
        event = st.dataframe(
            show_df, width='stretch', hide_index=True, height=500,
            on_select="rerun", selection_mode="single-row"
        )
        
        # Экспорт
        csv = show_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Скачать CSV", csv, f"tasks_{datetime.now():%Y%m%d}.csv", mime="text/csv")
        
        # --- ИНСПЕКТОР ---
        if event.selection.rows:
            idx = event.selection.rows[0]
            selected_id = df.iloc[idx]['task_id']
            
            st.markdown(f"#### 🔍 Инспектор задачи: `{selected_id[:8]}...`")
            with st.spinner("Генерация отчета..."):
                res = get_task_inspector_report(active_db, selected_id)
                
            if "error" in res:
                st.error(res["error"])
            else:
                st.code(res["report_text"], language="text")
                
    except Exception as e:
        st.error(f"Ошибка загрузки задач: {e}")
        st.exception(e)
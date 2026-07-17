# src/audit/audit_module.py
"""
Модуль отображения журнала событий (Audit Log UI).
Отвечает за: отрисовку каскадных фильтров, таблицы логов и поиск по ВМ/Хостам.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st      # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd         # Работа с табличными данными и подготовка DataFrame для отображения
from datetime import datetime  # Форматирование имен файлов при экспорте CSV

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from .audit_utils import (
    load_audit_infrastructure_maps,  # Загрузка связей ДЦ/Кластеры/Хосты для каскадных фильтров
    fetch_audit_logs                 # Выполнение параметризованного SQL-запроса к audit_log
)

def render_audit_log(active_db):
    
    # Загружаем только справочники для Хостов и Кластеров (ВМ будем искать текстом)
    maps = load_audit_infrastructure_maps(active_db)
    
    # --- СТРОКА 1: ФИЛЬТРЫ ИНФРАСТРУКТУРЫ И ПОИСК ---
    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
    
    with c1:
        dc_opts = ['Все ДЦ'] + sorted(set(maps["dc_id_to_name"].values()))
        sel_dc = st.selectbox("Дата-центр", dc_opts, key="audit_dc")
        
    with c2:
        cl_opts = ['Все кластеры']
        if sel_dc != 'Все ДЦ':
            dc_id = next((k for k,v in maps["dc_id_to_name"].items() if v == sel_dc), None)
            valid_cls = [maps["cluster_id_to_name"][cid] for cid in maps["dc_to_clusters"].get(dc_id, []) if cid in maps["cluster_id_to_name"]]
            cl_opts += sorted(valid_cls)
        else:
            cl_opts += sorted(set(maps["cluster_id_to_name"].values()))
        sel_cl = st.selectbox("Кластер", cl_opts, key="audit_cl")
        
    with c3:
        h_opts = ['Все хосты']
        if sel_cl != 'Все кластеры':
            cl_id = next((k for k,v in maps["cluster_id_to_name"].items() if v == sel_cl), None)
            valid_hosts = [maps["host_id_to_name"][hid] for hid in maps["cluster_to_hosts"].get(cl_id, []) if hid in maps["host_id_to_name"]]
            h_opts += sorted(valid_hosts)
        else:
            h_opts += sorted(set(maps["host_id_to_name"].values()))
        sel_host = st.selectbox("Хост", h_opts, key="audit_host")

    # Поле поиска ВМ (текстовое)
    with c4:
        search_vm = st.text_input("Поиск ВМ (имя/UUID)", placeholder="Например: tsk1-zabbix...", key="audit_vm_search")
        
    # --- СТРОКА 2: ВРЕМЯ, ВАЖНОСТЬ И ЛИМИТ ---
    t1, t2, t3, t4 = st.columns([2, 2, 1, 1])
    with t1: start_dt = st.datetime_input("С", value=None, key="audit_start")
    with t2: end_dt = st.datetime_input("По", value=None, key="audit_end")
    with t3: 
        sev_map = {"Все": "all", "Ошибки (≥3)": "errors", "Предупреждения (≥2)": "warnings"}
        sel_sev = st.selectbox("Важность", list(sev_map.keys()), key="audit_sev")
    with t4: limit_val = st.number_input("Лимит", 50, 10000, 500, step=50, key="audit_lim")
    
    # --- СБОР ПАРАМЕТРОВ ДЛЯ ЗАПРОСА ---
    host_id = next((k for k,v in maps["host_id_to_name"].items() if v == sel_host), None)
    
    # Передаем параметры в утилиту
    filters = {
        "host_id": host_id,
        "vm_search": search_vm.strip() if search_vm else None,
        "severity": sev_map[sel_sev],
        "start_dt": start_dt,
        "end_dt": end_dt
    }
    
    df = fetch_audit_logs(active_db, filters, limit_val)
    
    if df.empty:
        st.info("Нет записей по заданным критериям.")
        return
        
    # --- ОТОБРАЖЕНИЕ ТАБЛИЦЫ ---
    display_cols = {
        "log_time": "Время", "log_type_name": "Событие", "severity": "Ур.",
        "message": "Сообщение", "vds_name": "Хост", "vm_name": "ВМ", "user_name": "User"
    }
    
    # Формируем DataFrame для отображения
    show_df = df[[c for c in display_cols.keys()]].rename(columns=display_cols)
    
    # Стилизация уровня важности
    def color_sev(val):
        try:
            v = int(val)
            if v >= 3: return "color: red; font-weight: bold"
            if v == 2: return "color: orange"
        except: pass
        return ""
        
    styled = show_df.style.map(color_sev, subset=["Ур."])
    
    st.dataframe(
        styled, 
        width='stretch',
        hide_index=True, 
        height=600
    )
    
    # Экспорт
    csv = show_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 Скачать CSV", csv, f"audit_{datetime.now():%Y%m%d}.csv", mime="text/csv")
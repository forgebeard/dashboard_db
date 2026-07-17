# src/disks/disks_module.py
"""
Модуль отображения списка дисков и образов (UI).
Отвечает за: отрисовку фильтров, таблицы дисков и взаимодействие с инспектором.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st      # Фреймворк для построения веб-интерфейса дашборда
import pandas as pd         # Работа с табличными данными
from sqlalchemy import text # Безопасное формирование SQL-запросов

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os                   # Доступ к переменным окружения
import sys                  # Управление путями поиска модулей

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(__file__))
from core.db_utils import get_sqlalchemy_engine
from core.ui_utils import fix_uuid_columns
from disks.disks_utils import process_disks_dataframe
from core.constants import IMAGE_STATUS_MAP

def render_disks_list(active_db, cluster_meta):
    st.subheader("Поиск и анализ дисков/образов")

    # --- СТРОКА 1: ФИЛЬТРЫ И ПОИСК ---
    col_status, col_search_disk, col_search_vm, col_search_sd = st.columns([2, 2, 2, 2])
    
    with col_status:
        # Создаем список статусов для мультивыбора. По умолчанию ничего не выбрано (показываем всё)
        status_options = list(IMAGE_STATUS_MAP.values())
        selected_statuses = st.multiselect(
            "Фильтр по статусу:", 
            options=status_options,
            default=[], 
            key="disk_status_filter",
            placeholder="Все статусы"
        )

    with col_search_disk:
        search_disk = st.text_input(
            "Поиск диска:", 
            placeholder="Имя или UUID...", 
            key="disk_search_name"
        )

    with col_search_vm:
        search_vm = st.text_input(
            "Поиск ВМ:", 
            placeholder="Имя ВМ...", 
            key="disk_search_vm"
        )

    with col_search_sd:
        search_sd = st.text_input(
            "Поиск хранилища:", 
            placeholder="Имя домена...", 
            key="disk_search_sd"
        )

    # --- ПОЛУЧЕНИЕ ДАННЫХ ---
    # Получаем коды статусов на основе выбора пользователя
    status_codes = [k for k, v in IMAGE_STATUS_MAP.items() if v in selected_statuses]
    
    base_sql = """
        SELECT 
            bd.disk_alias,
            i.image_guid::text,
            i.imagestatus,
            i.size,
            did.actual_size,
            i.active,
            vm.vm_name,
            sd.storage_name
        FROM images i
        JOIN base_disks bd ON i.image_group_id = bd.disk_id
        LEFT JOIN disk_image_dynamic did ON i.image_guid = did.image_id
        LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
        LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
        LEFT JOIN vm_device vd ON bd.disk_id = vd.device_id
        LEFT JOIN vm_static vm ON vd.vm_id = vm.vm_guid
        WHERE 1=1
    """
    
    conditions = []
    params = {}
    
    # Фильтр по статусу
    if status_codes:
        conditions.append("i.imagestatus IN :statuses")
        params['statuses'] = tuple(status_codes)
            
    # Поиск по диску
    if search_disk:
        conditions.append("(LOWER(bd.disk_alias) LIKE LOWER(:search_disk) OR i.image_guid::text LIKE LOWER(:search_disk))")
        params['search_disk'] = f"%{search_disk}%"

    # Поиск по ВМ
    if search_vm:
        conditions.append("LOWER(vm.vm_name) LIKE LOWER(:search_vm)")
        params['search_vm'] = f"%{search_vm}%"

    # Поиск по хранилищу
    if search_sd:
        conditions.append("LOWER(sd.storage_name) LIKE LOWER(:search_sd)")
        params['search_sd'] = f"%{search_sd}%"
        
    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
    
    # Ограничиваем выборку последними 500 записями для производительности, если нет точного поиска
    # Если есть поиск - снимаем лимит, так как пользователь явно что-то ищет
    if not any([search_disk, search_vm, search_sd]):
        base_sql += " ORDER BY i.creation_date DESC LIMIT 500"
    else:
        base_sql += " ORDER BY bd.disk_alias"

    try:
        engine = get_sqlalchemy_engine(active_db)
        raw_df = pd.read_sql(text(base_sql), engine, params=params if params else None)
        engine.dispose()
    except Exception as e:
        st.error(f"Ошибка загрузки данных о дисках: {e}")
        return

    if raw_df.empty:
        st.info("Диски по заданным критериям не найдены.")
        return

    # Исправляем UUID и обрабатываем DataFrame
    raw_df = fix_uuid_columns(raw_df)
    display_df = process_disks_dataframe(raw_df)

    # --- ОТРИСОВКА ТАБЛИЦЫ ---
    def status_color(val):
        val_str = str(val)
        if 'LOCKED' in val_str or 'ILLEGAL' in val_str: return 'color: red; font-weight: bold'
        if 'MERGING' in val_str: return 'color: orange'
        return ''

    styled_df = display_df.style.map(status_color, subset=['Статус'])

    column_config = {
        "Имя диска": st.column_config.TextColumn(width="medium"),
        "UUID образа": st.column_config.TextColumn(width="small"),
        "Вирт. размер": st.column_config.TextColumn(width="small"),
        "Факт. размер": st.column_config.TextColumn(width="small"),
    }

    # Адаптивная высота: если записей мало - показываем все, если много - скролл
    row_count = len(display_df)
    dynamic_height = min(row_count * 35 + 70, 600) # 35px на строку + 70px на заголовок, макс 600px

    event = st.dataframe(
        styled_df,
        width='stretch', 
        hide_index=True, 
        on_select="rerun",
        selection_mode="single-row", 
        column_config=column_config, 
        height=dynamic_height # <-- ВОТ ЗДЕСЬ МАГИЯ
    )

    # --- ИНСПЕКТОР ---
    if event.selection.rows:
        idx = event.selection.rows[0]
        selected_uuid = display_df.iloc[idx]['UUID образа']
        
        st.markdown(f"#### 🔍 Инспектор диска: {display_df.iloc[idx]['Имя диска']}")
        st.caption(f"UUID: `{selected_uuid}` | ВМ: {display_df.iloc[idx]['ВМ']}")
        
        with st.spinner("Генерация полного отчета DISK-Inspector..."):
            from disks.disks_inspector_sql import get_disk_inspector_report
            result = get_disk_inspector_report(active_db, selected_uuid)
            
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")
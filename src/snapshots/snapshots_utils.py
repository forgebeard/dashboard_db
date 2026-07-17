# src/snapshots/snapshots_utils.py
"""
Утилиты для работы с данными снапшотов.
Отвечает за: построение SQL-запросов и подготовку DataFrame для отображения.
Загрузка связей инфраструктуры централизована в core.data_loader.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd          # Работа с табличными данными и выполнение SQL-запросов
from sqlalchemy import text  # Безопасное формирование параметризованных SQL-запросов
import streamlit as st       # Фреймворк UI (используется для вывода ошибок/предупреждений)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL
from core.constants import IMAGE_STATUS_MAP      # Глобальный справочник статусов образов


def fetch_snapshots_data(
    active_db: str, 
    filters: tuple[str, str, str, str], 
    dc_id_to_name: dict[str, str],
    clusters: dict[str, str]
) -> pd.DataFrame:
    """
    Выполняет SQL-запрос к снапшотам с учетом выбранных фильтров.
    Объединяет snapshots + images + vm_static + cluster для полноты данных.
    
    Args:
        active_db: Имя активной базы данных
        filters: Кортеж (dc_name, cluster_name, search_term, status_filter)
        dc_id_to_name: Словарь {dc_id: dc_name} из cluster_meta
        clusters: Словарь {cluster_id: cluster_name} из cluster_meta
        
    Returns:
        DataFrame с сырыми данными снапшотов или пустой DF при ошибке
    """
    selected_dc_name, selected_cluster_name, search_term, selected_status = filters
    
    # Определяем ID ДЦ и Кластера по именам из метаданных
    target_dc_id = None
    if selected_dc_name != 'Все ДЦ':
        target_dc_id = next((k for k, v in dc_id_to_name.items() if v == selected_dc_name), None)
        
    target_cid = None
    if selected_cluster_name != 'Все кластеры':
        target_cid = next((k for k, v in clusters.items() if v == selected_cluster_name), None)

    base_sql = """
        SELECT 
            s.snapshot_id::text AS snapshot_id,
            s.vm_id::text AS _vm_id,
            v.vm_name,
            c.name AS cluster_name,
            sp.name AS dc_name,
            s.creation_date,
            s.snapshot_type,
            s.description AS snapshot_desc,
            i.image_guid::text AS image_guid,
            i.size,
            i.imagestatus AS _image_status_code,
            sd.storage_name,
            i.active
        FROM snapshots s
        JOIN vm_static v ON s.vm_id = v.vm_guid
        JOIN cluster c ON v.cluster_id = c.cluster_id
        LEFT JOIN storage_pool sp ON c.storage_pool_id = sp.id
        LEFT JOIN images i ON s.snapshot_id = i.vm_snapshot_id
        LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
        LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
        WHERE TRUE
    """
    
    conditions = []
    sql_params = {}
    
    if target_dc_id:
        conditions.append("c.storage_pool_id = :dc_id")
        sql_params['dc_id'] = target_dc_id
            
    if target_cid:
        conditions.append("v.cluster_id = :cluster_id")
        sql_params['cluster_id'] = target_cid
            
    if search_term:
        conditions.append("(LOWER(v.vm_name) LIKE LOWER(:search) OR s.snapshot_id::text LIKE LOWER(:search))")
        sql_params['search'] = f"%{search_term}%"
        
    if selected_status and selected_status != 'Все статусы':
        # Маппинг текстового статуса в код через глобальную константу
        status_codes = [k for k, v in IMAGE_STATUS_MAP.items() if v == selected_status]
        if status_codes:
            # Формируем именованные параметры (:status_0, :status_1...)
            param_names = [f":status_{i}" for i in range(len(status_codes))]
            placeholders = ", ".join(param_names)
            conditions.append(f"i.imagestatus IN ({placeholders})")
            
            # Добавляем каждый код как отдельный именованный параметр
            for i, code in enumerate(status_codes):
                sql_params[f'status_{i}'] = code

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
        
    base_sql += " ORDER BY s.creation_date DESC"

    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(base_sql), engine, params=sql_params if sql_params else None)
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки снапшотов: {e}")
        return pd.DataFrame()


def process_snapshot_dataframe(
    df: pd.DataFrame, 
    dc_id_to_name: dict[str, str], 
    clusters: dict[str, str]
) -> pd.DataFrame:
    """
    Обрабатывает сырой DataFrame: добавляет читаемые статусы, форматирует размер.
    Корректно обрабатывает float-коды статусов (из-за NaN в LEFT JOIN).
    
    Args:
        df: Сырой DataFrame из fetch_snapshots_data
        dc_id_to_name: Словарь {dc_id: dc_name}
        clusters: Словарь {cluster_id: cluster_name}
        
    Returns:
        Отформатированный DataFrame для отображения в таблице
    """
    if df.empty:
        return pd.DataFrame()

    # Расширенный маппинг статусов образов oVirt Engine
    EXTENDED_IMAGE_STATUS_MAP = {
        0: "UNASSIGNED",
        1: "OK",
        2: "LOCKED",
        3: "ILLEGAL",
        4: "MERGING",
        5: "UPLOADING",
        6: "PAUSED",
        7: "RESUMING",
        8: "NOT_RESPONDING",
        9: "POWERING_DOWN",
    }
    
    # Преобразуем float-коды в int (округляя NaN до None) перед маппингом
    def safe_map_status(code):
        if pd.isna(code):
            return "—"
        try:
            int_code = int(code)
            return EXTENDED_IMAGE_STATUS_MAP.get(int_code, f"Code {int_code}")
        except (ValueError, TypeError):
            return f"Code {code}"
            
    df['Статус образа'] = df['_image_status_code'].apply(safe_map_status)
    
    # Конвертируем байты в ГБ для удобного отображения
    # Обработка NaN: если size отсутствует, показываем None или 0
    df['Размер'] = df['size'].apply(lambda x: round(x / (1024**3), 2) if pd.notna(x) else None)
    
    # Формируем итоговый набор колонок для UI
    display_df = df[[
        'vm_name', 'snapshot_id', 'creation_date', 'snapshot_type', 
        'Размер', 'Статус образа', 'storage_name', '_image_status_code', '_vm_id'
    ]].copy()
    
    display_df.columns = [
        'Имя ВМ', 'UUID снапшота', 'Дата создания', 'Тип', 
        'Размер', 'Статус образа', 'Хранилище', '_image_status_code', '_vm_id'
    ]
    
    return display_df
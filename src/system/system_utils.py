# src/system/system_utils.py
"""
Утилиты для раздела «Системные».
Отвечает за: сбор разнородных данных в единую таблицу и расчет сводки.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd
from sqlalchemy import text
import streamlit as st

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine
from core.ui_utils import fix_uuid_columns


def _get_unified_system_data(active_db: str) -> pd.DataFrame:
    """
    Собирает данные из системных таблиц в единый нормализованный DataFrame.
    
    Структура результата:
    - type: Тип объекта (Session, Fencing, Provider, Quota, Transfer, Option)
    - name: Имя/Идентификатор объекта
    - status: Статус или основное значение
    - details: Дополнительные детали (IP, URL, Limits)
    - source: Исходная таблица БД
    """
    engine = get_sqlalchemy_engine(active_db)
    frames = []

    try:
        # 1. Активные сессии
        df_sess = pd.read_sql(text("""
            SELECT 
                'Session' AS type,
                user_name AS name,
                'Active' AS status,
                source_ip AS details,
                'engine_sessions' AS source
            FROM engine_sessions
        """), engine)
        if not df_sess.empty: frames.append(df_sess)

        # 2. Агенты фенсинга (с именами хостов)
        df_fence = pd.read_sql(text("""
            SELECT 
                'Fencing' AS type,
                v.vds_name AS name,
                fa.type AS status,
                CONCAT(fa.ip, ':', COALESCE(fa.port::text, '')) AS details,
                'fence_agents' AS source
            FROM fence_agents fa
            JOIN vds_static v ON fa.vds_id = v.vds_id
        """), engine)
        if not df_fence.empty: frames.append(df_fence)

        # 3. Провайдеры
        df_prov = pd.read_sql(text("""
            SELECT 
                'Provider' AS type,
                name,
                provider_type AS status,
                url AS details,
                'providers' AS source
            FROM providers
        """), engine)
        if not df_prov.empty: frames.append(df_prov)

        # 4. Квоты (объединенные с лимитами)
        # Примечание: точный расчет % использования требует сложных JOIN'ов с vm_static/vds_static.
        # Для первой версии показываем пороги триггеров как контекст.
        df_quota = pd.read_sql(text("""
            SELECT 
                'Quota' AS type,
                q.quota_name AS name,
                CONCAT('Cluster:', q.threshold_cluster_percentage, '% | Storage:', q.threshold_storage_percentage, '%') AS status,
                CONCAT('Grace: ', q.grace_cluster_percentage, '%/') AS details,
                'quota' AS source
            FROM quota q
        """), engine)
        if not df_quota.empty: frames.append(df_quota)

        # 5. Активные передачи образов
        df_trans = pd.read_sql(text("""
            SELECT 
                'Transfer' AS type,
                disk_id::text AS name,
                CASE phase 
                    WHEN 0 THEN 'Initializing' 
                    WHEN 1 THEN 'Transferring' 
                    WHEN 2 THEN 'Finished' 
                    ELSE 'Unknown' 
                END AS status,
                CONCAT(bytes_sent::text, ' / ', bytes_total::text, ' bytes') AS details,
                'image_transfers' AS source
            FROM image_transfers
            WHERE active = true
        """), engine)
        if not df_trans.empty: frames.append(df_trans)

        # 6. Измененные опции движка (только кастомные)
        df_opts = pd.read_sql(text("""
            SELECT 
                'Option' AS type,
                option_name AS name,
                option_value AS status,
                CONCAT('Default: ', COALESCE(default_value, 'N/A')) AS details,
                'vdc_options' AS source
            FROM vdc_options
            WHERE option_value != default_value 
              AND default_value IS NOT NULL
            LIMIT 200 -- Ограничение, чтобы не перегрузить UI
        """), engine)
        if not df_opts.empty: frames.append(df_opts)

        # Объединяем все части
        if frames:
            result = pd.concat(frames, ignore_index=True)
            return fix_uuid_columns(result)
            
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Ошибка сбора системных данных: {e}")
        return pd.DataFrame()


def get_system_summary(active_db: str) -> dict:
    """
    Быстрая сводка для верхней панели.
    """
    summary = {
        "schema_version": "—",
        "sessions_count": 0,
        "fence_configured": 0,
        "active_transfers": 0,
        "custom_options": 0
    }
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        
        # Версия схемы
        df_ver = pd.read_sql(text("SELECT version FROM schema_version WHERE current = true LIMIT 1"), engine)
        if not df_ver.empty:
            summary["schema_version"] = df_ver.iloc[0]['version']
            
        # Счетчики
        counts = pd.read_sql(text("""
            SELECT 
                (SELECT COUNT(*) FROM engine_sessions) as sess,
                (SELECT COUNT(*) FROM fence_agents) as fence,
                (SELECT COUNT(*) FROM image_transfers WHERE active = true) as trans,
                (SELECT COUNT(*) FROM vdc_options WHERE option_value != default_value AND default_value IS NOT NULL) as opts
        """), engine)
        
        if not counts.empty:
            row = counts.iloc[0]
            summary["sessions_count"] = int(row['sess'])
            summary["fence_configured"] = int(row['fence'])
            summary["active_transfers"] = int(row['trans'])
            summary["custom_options"] = int(row['opts'])
            
    except Exception as e:
        st.warning(f"Не удалось загрузить сводку: {e}")
        
    return summary
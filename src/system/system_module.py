# src/system/system_module.py
"""
UI-модуль раздела «Системные».
Отвечает за: отображение единой таблицы системных объектов, фильтры и сводку.
Приведен к единому виду с другими разделами дашборда.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st
import pandas as pd

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from system.system_utils import _get_unified_system_data, get_system_summary
from system.system_diagnostics import render_system_diagnostics


def render_system_list(active_db: str, cluster_meta: dict) -> None:
    """
    Отрисовывает интерфейс раздела «Системные» в едином стиле.
    
    Args:
        active_db: Имя активной базы данных
        cluster_meta: Метаданные инфраструктуры (для контекста хостов)
    """
    # --- 1. КОМПАКТНАЯ СВОДКА («ПУЛЬС СИСТЕМЫ») ---
    summary = get_system_summary(active_db)
    
    col_metrics, col_spacer, col_status = st.columns([4, 1, 2])
    
    with col_metrics:
        metrics_str = (
            f"**Версия:** `{summary['schema_version']}` &nbsp;|&nbsp; "
            f"**Сессии:** {summary['sessions_count']} &nbsp;|&nbsp; "
            f"**Фенсинг:** {summary['fence_configured']} хост(ов) &nbsp;|&nbsp; "
            f"**Трансферы:** {summary['active_transfers']} &nbsp;|&nbsp; "
            f"**Кастомные опции:** {summary['custom_options']}"
        )
        st.markdown(metrics_str)
        
    with col_status:
        host_count = len(cluster_meta.get('hosts', {}))
        if host_count > 0 and summary['fence_configured'] == 0:
            st.warning("⚠️ Хосты есть, но фенсинг не настроен!", icon="️")
        elif summary['fence_configured'] > 0:
            st.success(f"✅ Фенсинг активен", icon="✅")
        else:
            st.info("️ Нет данных о хостах", icon="ℹ️")

    # --- 2. ФИЛЬТРЫ (как в Хостах/ВМ) ---
    col_type, col_search = st.columns([1, 3])
    
    type_options = ['Все объекты', 'Session', 'Fencing', 'Provider', 'Quota', 'Transfer', 'Option']
    
    with col_type:
        selected_type = st.selectbox("Тип объекта:", type_options, key="sys_type_filter")
        
    with col_search:
        search_term = st.text_input(
            "Поиск (Имя / IP / Ключ):", 
            placeholder="Например: admin, ipmilan, ovirt-provider...", 
            key="sys_search"
        )

    # --- 3. ЗАГРУЗКА И ОБРАБОТКА ДАННЫХ ---
    raw_df = _get_unified_system_data(active_db)
    
    if not raw_df.empty:
        # Фильтр по типу
        if selected_type != 'Все объекты':
            raw_df = raw_df[raw_df['type'] == selected_type]
            
        # Поиск по всем текстовым полям
        if search_term:
            mask = raw_df.apply(
                lambda row: row.astype(str).str.contains(search_term, case=False).any(), 
                axis=1
            )
            raw_df = raw_df[mask]

    # --- 4. СВОДКА И ЭКСПОРТ ---
    col_info, col_spacer, col_btn = st.columns([2, 6, 1])
    
    with col_info:
        st.markdown(f"**Объектов:** {len(raw_df)}")
        
    with col_btn:
        csv = raw_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📥 Скачать CSV", csv, "system_objects.csv", "text/csv", 
            key='download-system-csv', use_container_width=True
        )

    # --- 5. ЕДИНАЯ ТАБЛИЦА С ЦВЕТОВОЙ ИНДИКАЦИЕЙ ---
    
    def highlight_row(row):
        """Цветовая индикация строк в зависимости от типа и статуса."""
        if row['type'] == 'Transfer' and 'Transferring' in str(row['status']):
            return ['background-color: rgba(243, 156, 18, 0.15)'] * len(row)
        if row['type'] == 'Quota':
            return ['background-color: rgba(52, 152, 219, 0.1)'] * len(row)
        if row['type'] == 'Fencing':
            return ['background-color: rgba(46, 204, 113, 0.1)'] * len(row)
        return [''] * len(row)

    column_config = {
        "type": st.column_config.TextColumn("Тип", width="small"),
        "name": st.column_config.TextColumn("Объект", width="medium"),
        "status": st.column_config.TextColumn("Статус / Значение", width="medium"),
        "details": st.column_config.TextColumn("Контекст / Детали", width="large"),
        "source": st.column_config.TextColumn("Источник", width="small"),
    }

    if not raw_df.empty:
        table_height = min(max(len(raw_df) * 40 + 60, 200), 500)
        
        styled_df = raw_df.style.apply(highlight_row, axis=1)
        
        st.dataframe(
            styled_df,
            width='stretch', 
            height=table_height, 
            hide_index=True,
            column_config=column_config
        )
    else:
        st.info("Объекты не найдены по выбранным критериям.")
    
    # --- 6. ДИАГНОСТИКА (сырые таблицы) ---
    render_system_diagnostics(active_db)

def fetch_system_table(active_db: str, table_name: str, limit: int) -> pd.DataFrame:
    """
    Загружает данные отдельной системной таблицы для диагностики.
    Используется ТОЛЬКО в system_diagnostics.py.
    """
    effective_limit = 50 if table_name == 'vdc_db_log' else limit
    
    try:
        engine = get_sqlalchemy_engine(active_db)
        query = f"SELECT * FROM {table_name} ORDER BY 1 DESC LIMIT {effective_limit}"
        df = pd.read_sql_query(text(query), engine)
        
        # Фиксируем UUID
        df = fix_uuid_columns(df)
        
        # Маскируем чувствительные данные
        sensitive_map = {
            'fence_agents': ['agent_password'],
            'providers': ['auth_password'],
            'libvirt_secrets': ['secret_value'],
            'engine_sessions': ['user_id', 'source_ip'],
        }
        
        for col in sensitive_map.get(table_name, []):
            if col in df.columns:
                df[col] = '***MASKED***'
                
        return df
        
    except Exception as e:
        st.error(f"Ошибка загрузки `{table_name}`: {e}")
        return pd.DataFrame()
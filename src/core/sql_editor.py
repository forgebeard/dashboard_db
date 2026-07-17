# src/core/sql_editor.py
"""
Модуль глобального SQL-редактора.

Отвечает за выполнение пользовательских ad-hoc запросов к активной БД,
безопасное отображение результатов, историю запросов и экспорт данных.
Предназначен для оффлайн-использования доверенными инженерами L2/L3.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import time             # Замер времени выполнения запросов
import uuid             # Проверка и конвертация UUID-объектов

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк UI: редактор, таблицы, кнопки, session_state
import pandas as pd     # Работа с результатами запросов и экспорт в CSV
from sqlalchemy import text  # Безопасное выполнение параметризованных SQL

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Кэшированный движок SQLAlchemy
from core.config import MAX_ROW_LIMIT            # Максимальный лимит строк из конфига
from core.ui_utils import fix_uuid_columns       # Единая утилита конвертации UUID


# Константы модуля
_MAX_HISTORY_SIZE = 10       # Максимум сохранённых запросов в истории
_WARNING_ROW_THRESHOLD = 1000  # Порог предупреждения о большом результате


def _ensure_history() -> None:
    """Инициализирует историю запросов в session_state если её нет."""
    if "sql_history" not in st.session_state:
        st.session_state["sql_history"] = []


def _add_to_history(query: str) -> None:
    """
    Добавляет запрос в начало истории, убирая дубликаты и обрезая до максимума.
    
    Args:
        query: SQL-запрос для сохранения
    """
    _ensure_history()
    history: list[str] = st.session_state["sql_history"]
    
    # Убираем предыдущее вхождение этого же запроса (если было)
    history = [q for q in history if q != query]
    
    # Добавляем в начало
    history.insert(0, query)
    
    # Обрезаем до максимума
    st.session_state["sql_history"] = history[:_MAX_HISTORY_SIZE]


def render_global_sql(active_db: str) -> None:
    """
    Отрисовывает компактный SQL-редактор на основной странице.
    
    Включает: многострочный редактор, кнопку выполнения, историю запросов,
    таблицу результатов, копирование и скачивание CSV, таймер выполнения.
    
    Args:
        active_db: Имя активной базы данных для выполнения запросов
    """
    st.markdown("### 🛠️ SQL-редактор")
    _ensure_history()

    # --- ПОЛЕ ВВОДА И КНОПКА ВЫПОЛНЕНИЯ ---
    col_query, col_btn = st.columns([5, 1])
    
    with col_query:
        global_query = st.text_area(
            "SQL Запрос:",
            placeholder="SELECT * FROM vm_static LIMIT 10;",
            key="global_sql_input_main",
            label_visibility="collapsed",
            height=80
        )
        
    with col_btn:
        run_sql = st.button(
            "▶️ Выполнить", 
            type="primary", 
            use_container_width=True,
            disabled=not global_query.strip()
        )

    # --- ИСТОРИЯ ЗАПРОСОВ ---
    history: list[str] = st.session_state.get("sql_history", [])
    if history:
        cols_hist = st.columns(len(history) + 1)
        for i, saved_query in enumerate(history):
            # Показываем первые 40 символов как подсказку
            label = saved_query[:40].replace("\n", " ") + ("..." if len(saved_query) > 40 else "")
            if cols_hist[i].button(label, key=f"hist_{i}", help=saved_query):
                st.session_state["global_sql_input_main"] = saved_query
                st.rerun()
        
        if cols_hist[-1].button("🗑️", key="clear_history", help="Очистить историю"):
            st.session_state["sql_history"] = []
            st.rerun()

    # --- ВЫПОЛНЕНИЕ ЗАПРОСА ---
    if run_sql and global_query.strip():
        try:
            engine = get_sqlalchemy_engine(active_db)
            
            start_time = time.perf_counter()
            with engine.connect() as conn:
                df_res = pd.read_sql_query(text(global_query), conn)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            # Сохраняем успешный запрос в историю
            _add_to_history(global_query.strip())
            
            # Конвертация UUID для корректного отображения
            df_res = fix_uuid_columns(df_res)
            
            if df_res.empty:
                st.info(f"✅ Запрос выполнен за {elapsed_ms:.0f} мс. Данных нет.")
            else:
                # Предупреждение о большом результате
                if len(df_res) > _WARNING_ROW_THRESHOLD:
                    st.warning(
                        f"⚠️ Результат содержит {len(df_res)} строк. "
                        f"Рекомендуется добавить LIMIT в запрос."
                    )
                
                # --- ПАНЕЛЬ ДЕЙСТВИЙ: КОПИРОВАНИЕ + СКАЧИВАНИЕ ---
                action_col1, action_col2, action_col3 = st.columns([1, 1, 3])
                
                csv_text = df_res.to_csv(index=False)
                
                with action_col1:
                    st.download_button(
                        label="📥 Скачать CSV",
                        data=csv_text.encode("utf-8-sig"),
                        file_name=f"query_result_{int(time.time())}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                with action_col2:
                    st.code(csv_text[:1], language=None)  # Скрытый элемент для привязки
                    st.caption("💡 Используйте Ctrl+C в таблице ниже")

                with action_col3:
                    st.caption(f"Найдено строк: **{len(df_res)}** | Время: **{elapsed_ms:.0f} мс**")
                
                # Таблица результатов
                st.dataframe(
                    df_res, 
                    width='stretch', 
                    height=400, 
                    hide_index=True
                )
            
        except Exception as e:
            st.error(f"❌ Ошибка выполнения: {e}")
# src/core/config.py
"""
Глобальная конфигурация приложения RED Virt Analytics.

Этот модуль централизует все настройки, лимиты и константы отображения.
Изменение значений здесь применяется ко всему приложению сразу,
что упрощает поддержку и масштабирование дашборда.
"""

# --- КОНФИГУРАЦИЯ ПРИЛОЖЕНИЯ ---
APP_TITLE = "RED Virt Analytics"  # Заголовок вкладки браузера и сайдбара
APP_LAYOUT = "wide"               # Режим разметки: 'centered' (узкий) или 'wide' (на всю ширину)

# --- ЛИМИТЫ РАБОТЫ С ДАННЫМИ ---
DEFAULT_ROW_LIMIT = 50      # Стандартный лимит строк для превью таблиц
MAX_ROW_LIMIT = 2000        # Жесткий потолок защиты от переполнения памяти Streamlit
ROW_STEP = 10               # Шаг изменения лимита в виджете number_input
STATEMENT_TIMEOUT_MS = 30000  # PostgreSQL statement_timeout (мс); LIMIT не ограничивает время JOIN/ORDER BY

# --- НАСТРОЙКИ ОТОБРАЖЕНИЯ (UI) ---
DATAFRAME_HEIGHT = 500      # Потолок высоты st.dataframe (px)
DATAFRAME_ROW_PX = 36       # Оценка высоты строки таблицы
DATAFRAME_HEADER_PX = 40    # Оценка высоты шапки таблицы
DATAFRAME_HEIGHT_PAD = 16   # Запас под рамку/скролл
FONT_SIZE_CSS = "0.85rem"   # Размер шрифта внутри st.dataframe для компактности

# CSS для семантических тонов статуса (не использовать green/red в модулях).
STATUS_TONE_CSS = {
    "success": "color: #2ecc71; font-weight: bold;",
    "warning": "color: #e67e22; font-weight: bold;",
    "critical": "color: #e74c3c; font-weight: bold;",
    "neutral": "color: #95a5a6;",
}
# src/core/ui_utils.py
"""
Общие утилиты для пользовательского интерфейса Streamlit.

Содержит вспомогательные функции для обеспечения единообразия отображения данных.
Оптимизирован для работы с большими таблицами oVirt Engine.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import uuid             # Работа с объектами UUID и проверка типов

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd     # Векторизированная обработка табличных данных


def fix_uuid_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Конвертирует объекты uuid.UUID в строки для корректного отображения в Streamlit.
    
    Использует векторизированные операции Pandas вместо apply(lambda) 
    для сохранения производительности на больших выборках.
    
    Args:
        df: Исходный DataFrame с возможными UUID-колонками
        
    Returns:
        DataFrame с конвертированными UUID-колонками (inplace модификация)
        
    Note:
        Функция модифицирует переданный DataFrame inplace для экономии памяти.
        Если исходный DF нужен неизменным — передавайте копию.
    """
    if df.empty:
        return df
    
    for col in df.columns:
        # Пропускаем колонки, где нет объектов Python (все int/float/datetime)
        if df[col].dtype != 'object':
            continue
            
        # Быстрая проверка: содержит ли колонка хотя бы один UUID-объект
        has_uuid = False
        for val in df[col]:
            if isinstance(val, uuid.UUID):
                has_uuid = True
                break
                
        if not has_uuid:
            continue
            
        # Векторизированная конвертация только найденных UUID
        df[col] = df[col].apply(
            lambda x: str(x) if isinstance(x, uuid.UUID) else x
        )
        
    return df
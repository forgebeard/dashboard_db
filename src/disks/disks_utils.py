# src/disks/disks_utils.py
"""
Утилиты для работы с дисками и образами (Disks & Images).
Отвечает за: форматирование размеров, подготовку DataFrame и маппинг статусов.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd         # Работа с табличными данными

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from core.constants import IMAGE_STATUS_MAP  # Глобальный справочник статусов образов

def format_size_bytes(size_bytes):
    """Конвертирует байты в читаемый формат (ГБ)."""
    if size_bytes is None or pd.isna(size_bytes):
        return "—"
    try:
        gb = float(size_bytes) / (1024**3)
        return f"{gb:.2f} ГБ"
    except (ValueError, TypeError):
        return "—"

def process_disks_dataframe(df):
    """
    Обрабатывает сырой DataFrame с информацией о дисках.
    Добавляет человеко-понятные лейблы и форматирует размеры.
    """
    if df.empty:
        return pd.DataFrame()

    # Маппинг статусов из констант
    df['status_label'] = df['imagestatus'].map(IMAGE_STATUS_MAP).fillna(f"Code {df['imagestatus']}")
    
    # Форматирование размеров
    df['virt_size_fmt'] = df['size'].apply(format_size_bytes)
    df['actual_size_fmt'] = df['actual_size'].apply(format_size_bytes)

    # Выбираем и переименовываем колонки для UI
    display_df = df[[
        'disk_alias', 
        'image_guid', 
        'status_label', 
        'vm_name', 
        'storage_name', 
        'virt_size_fmt', 
        'actual_size_fmt',
        'active'
    ]].copy()
    
    display_df.columns = [
        'Имя диска', 
        'UUID образа', 
        'Статус', 
        'ВМ', 
        'Хранилище', 
        'Вирт. размер', 
        'Факт. размер',
        'Активен'
    ]
    
    return display_df
"""
Загрузчик данных атласа схемы БД.
Автоматически сканирует директорию data/ и объединяет все JSON-файлы справочника.
"""

import json
from pathlib import Path
import streamlit as st

# Путь к директории со справочниками (теперь указываем на подпапку data)
ATLAS_DIR = Path(__file__).resolve().parent / "data"

def load_atlas_data() -> dict:
    """
    Загружает данные из всех JSON-файлов в директории ATLAS_DIR.
    
    Returns:
        Словарь вида {"tables": {table_name: metadata}}
    """
    if 'atlas_data' not in st.session_state:
        all_tables = {}
        
        # Проверяем существование папки data
        if not ATLAS_DIR.exists():
            st.warning(f"Директория {ATLAS_DIR} не найдена. Проверьте структуру проекта.")
            return {"tables": {}}

        json_files = sorted(ATLAS_DIR.glob("*.json"))
        
        if not json_files:
            st.warning(f"В директории {ATLAS_DIR} не найдено JSON-файлов справочника.")
            return {"tables": {}}

        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Поддержка структуры: { "group": "...", "tables": {...} }
                if "tables" in data:
                    group_name = data.get("group", "Uncategorized")
                    tables = data["tables"]
                    
                    for table_name, metadata in tables.items():
                        if table_name in all_tables:
                            st.warning(f"⚠️ Обнаружен дубликат таблицы '{table_name}' в файле {file_path.name}. Пропускаю.")
                            continue
                        
                        # Добавляем информацию о группе прямо в метаданные
                        metadata['group'] = group_name
                        all_tables[table_name] = metadata
                        
            except json.JSONDecodeError:
                st.error(f"Ошибка чтения JSON файла: {file_path.name}")
            except Exception as e:
                st.error(f"Неожиданная ошибка при обработке {file_path.name}: {e}")

        st.session_state['atlas_data'] = {"tables": all_tables}
            
    return st.session_state['atlas_data']
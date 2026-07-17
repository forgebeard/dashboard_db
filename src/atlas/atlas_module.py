"""
Главный модуль справочника схемы БД (Schema Atlas).
Координирует загрузку данных, фильтрацию и отрисовку.
"""

import streamlit as st
from collections import defaultdict

# Внутренние импорты пакета atlas
from .data_loader import load_atlas_data
from .renderer import render_group_section


def render_schema_atlas() -> None:
    """
    Точка входа в модуль справочника.
    """
    # 1. Загрузка данных
    atlas = load_atlas_data()
    tables = atlas.get('tables', {})
    
    if not tables:
        st.info("Справочник пуст. Проверьте наличие JSON-файлов в папке src/atlas/data/")
        return

    # 2. Верхняя панель фильтров
    col_filter, col_search = st.columns([1, 3])
    
    groups = sorted(set(t['group'] for t in tables.values()))
    
    with col_filter:
        selected_group = st.selectbox(
            "Группа:", 
            ['Все группы'] + groups,
            key="atlas_group_filter"
        )
        
    with col_search:
        search_term = st.text_input(
            "Поиск (Таблица / Поле / Описание):", 
            placeholder="Например: vds_static, cluster_id...", 
            key="atlas_search"
        ).strip().lower()

    # 3. Логика фильтрации и "Умная" сортировка
    filtered_tables = {}
    for name, info in tables.items():
        name_lower = name.lower()
        desc_lower = info.get('summary', '').lower() or info.get('description', '').lower()
        
        # Проверяем поля таблицы (если они есть в структуре)
        fields_doc = info.get('fields_doc', {})
        fields_str = " ".join([k.lower() for k in fields_doc.keys()]) if fields_doc else ""
        
        matches_search = (
            not search_term or
            search_term in name_lower or 
            search_term in desc_lower or
            search_term in fields_str
        )
        
        matches_group = selected_group == 'Все группы' or info['group'] == selected_group
        
        if matches_search and matches_group:
            # Добавляем флаг для сортировки: True, если имя начинается с поискового запроса
            starts_with_query = name_lower.startswith(search_term) if search_term else False
            filtered_tables[name] = (info, starts_with_query)

    # Сортируем: сначала те, что начинаются с запроса, потом по алфавиту
    sorted_filtered = sorted(
        filtered_tables.items(), 
        key=lambda item: (not item[1][1], item[0])
    )

    st.markdown(f"**Найдено таблиц:** {len(sorted_filtered)}")
    st.divider()

    # 4. Группировка для отрисовки
    grouped = defaultdict(list)
    for name, (info, _) in sorted_filtered:
        grouped[info['group']].append((name, info))

    # Если выбрана конкретная группа, показываем только её
    display_groups = [selected_group] if selected_group != 'Все группы' else sorted(grouped.keys())

    for group_name in display_groups:
        if group_name in grouped:
            render_group_section(group_name, grouped[group_name])
"""
Рендерер интерфейса справочника схемы БД.
Строгий стиль: умная вложенность (убирает лишние слои для малых групп), 
все элементы свернуты по умолчанию.
"""

import streamlit as st


def render_table_card(table_name: str, info: dict) -> None:
    """Отрисовка карточки одной таблицы."""
    summary = info.get('summary', '')
    key_fields = set(info.get('key_fields', []))
    fields_doc = info.get('fields_doc', {})
    relations_doc = info.get('relations_doc', [])

    # expanded=False гарантирует, что таблица скрыта при открытии раздела
    with st.expander(f"`{table_name}` — {summary}" if summary else f"`{table_name}`", expanded=False):
        
        # Описание полей (включая PK-маркер)
        if fields_doc:
            st.markdown("**Описание полей:**")
            for field, desc in fields_doc.items():
                pk_marker = " `[PK]`" if field in key_fields else ""
                st.caption(f"- `{field}` — {desc}{pk_marker}")

        # Связи
        if relations_doc:
            st.markdown("**Связи:**")
            for rel in relations_doc:
                st.caption(f"- {rel}")


def render_group_section(group_name: str, tables_list: list) -> None:
    """Отрисовка группы таблиц с поддержкой вложенных подгрупп."""
    
    # Группа тоже свернута по умолчанию
    with st.expander(f"{group_name} ({len(tables_list)} табл.)", expanded=False):
        
        has_subgroups = any(t[1].get('subgroup') for t in tables_list)

        if has_subgroups:
            subgroups: dict[str, list] = {}
            no_subgroup_tables: list = []

            # Распределение таблиц по подгруппам
            for name, info in tables_list:
                sg = info.get('subgroup')
                if sg:
                    subgroups.setdefault(sg, []).append((name, info))
                else:
                    no_subgroup_tables.append((name, info))

            # Таблицы без подгрупп (если есть)
            if no_subgroup_tables:
                st.markdown("#### Прочие")
                for name, info in sorted(no_subgroup_tables, key=lambda x: x[0]):
                    render_table_card(name, info)

            # УМНАЯ ВЛОЖЕННОСТЬ: Если подгруппа всего одна И нет "прочих" таблиц,
            # убираем лишний слой экспандера для удобства навигации
            is_single_subgroup = len(subgroups) == 1 and not no_subgroup_tables
            
            if is_single_subgroup:
                # Рендерим таблицы напрямую, игнорируя имя единственной подгруппы
                sg_name = next(iter(subgroups))
                for name, info in sorted(subgroups[sg_name], key=lambda x: x[0]):
                    render_table_card(name, info)
            else:
                # Стандартная логика с вложенными экспандерами
                desired_order = ["Core", "Storage", "Network", "Config"]
                
                # Сначала рисуем в нужном порядке
                for sg_name in desired_order:
                    if sg_name in subgroups:
                        sg_tables = subgroups[sg_name]
                        with st.expander(f"{sg_name} ({len(sg_tables)} табл.)", expanded=False):
                            for name, info in sorted(sg_tables, key=lambda x: x[0]):
                                render_table_card(name, info)

                # Потом рисуем остальные (если вдруг появятся новые подгруппы)
                remaining = [sg for sg in sorted(subgroups.keys()) if sg not in desired_order]
                for sg_name in remaining:
                    sg_tables = subgroups[sg_name]
                    with st.expander(f"{sg_name} ({len(sg_tables)} табл.)", expanded=False):
                        for name, info in sorted(sg_tables, key=lambda x: x[0]):
                            render_table_card(name, info)
        else:
            # Если подгрупп нет, просто список таблиц
            for name, info in sorted(tables_list, key=lambda x: x[0]):
                render_table_card(name, info)
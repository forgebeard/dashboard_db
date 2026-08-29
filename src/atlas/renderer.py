"""
Рендерер интерфейса справочника схемы БД.
Строгий стиль: умная вложенность (убирает лишние слои для малых групп),
все элементы свернуты по умолчанию.
"""

import streamlit as st

from .data_loader import field_compat_note, release_badge_text


def render_table_card(table_name: str, info: dict) -> None:
    """Отрисовка карточки одной таблицы."""
    summary = info.get("summary", "")
    key_fields = set(info.get("key_fields", []))
    fields_doc = info.get("fields_doc", {})
    relations_doc = info.get("relations_doc", [])
    column_compat = info.get("column_compat") or {}
    badge = release_badge_text(info)

    title = f"`{table_name}` — {summary}" if summary else f"`{table_name}`"
    if badge:
        title = f"{title} · {badge}"

    with st.expander(title, expanded=False):
        if fields_doc:
            st.markdown("**Описание полей:**")
            for field, desc in fields_doc.items():
                pk_marker = " `[PK]`" if field in key_fields else ""
                note = field_compat_note(column_compat.get(field))
                extra = f" · {note}" if note else ""
                st.caption(f"- `{field}` — {desc}{pk_marker}{extra}")

        if relations_doc:
            st.markdown("**Связи:**")
            for rel in relations_doc:
                st.caption(f"- {rel}")


def render_group_section(group_name: str, tables_list: list) -> None:
    """Отрисовка группы таблиц с поддержкой вложенных подгрупп."""

    with st.expander(f"{group_name} ({len(tables_list)} табл.)", expanded=False):
        has_subgroups = any(t[1].get("subgroup") for t in tables_list)

        if has_subgroups:
            subgroups: dict[str, list] = {}
            no_subgroup_tables: list = []

            for name, info in tables_list:
                sg = info.get("subgroup")
                if sg:
                    subgroups.setdefault(sg, []).append((name, info))
                else:
                    no_subgroup_tables.append((name, info))

            if no_subgroup_tables:
                st.markdown("#### Прочие")
                for name, info in sorted(no_subgroup_tables, key=lambda x: x[0]):
                    render_table_card(name, info)

            is_single_subgroup = len(subgroups) == 1 and not no_subgroup_tables

            if is_single_subgroup:
                sg_name = next(iter(subgroups))
                for name, info in sorted(subgroups[sg_name], key=lambda x: x[0]):
                    render_table_card(name, info)
            else:
                desired_order = ["Core", "Storage", "Network", "Config"]

                for sg_name in desired_order:
                    if sg_name in subgroups:
                        sg_tables = subgroups[sg_name]
                        with st.expander(f"{sg_name} ({len(sg_tables)} табл.)", expanded=False):
                            for name, info in sorted(sg_tables, key=lambda x: x[0]):
                                render_table_card(name, info)

                remaining = [sg for sg in sorted(subgroups.keys()) if sg not in desired_order]
                for sg_name in remaining:
                    sg_tables = subgroups[sg_name]
                    with st.expander(f"{sg_name} ({len(sg_tables)} табл.)", expanded=False):
                        for name, info in sorted(sg_tables, key=lambda x: x[0]):
                            render_table_card(name, info)
        else:
            for name, info in sorted(tables_list, key=lambda x: x[0]):
                render_table_card(name, info)

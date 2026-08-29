"""
Главный модуль справочника схемы БД (Schema Atlas).
Координирует загрузку данных, фильтрацию и отрисовку.
"""

from collections import defaultdict

import streamlit as st

from .data_loader import (
    RELEASE_LABELS,
    format_changelog_details,
    format_changelog_intro,
    load_atlas_data,
    load_changelog,
    release_key_from_label,
    table_visible_for_release,
    visible_fields_doc,
)
from .renderer import render_group_section

_SCHEMA_OPTIONS = [RELEASE_LABELS["7.3"], RELEASE_LABELS["8"]]


def render_schema_atlas() -> None:
    """
    Точка входа в модуль справочника.
    """
    atlas = load_atlas_data()
    tables = atlas.get("tables", {})

    if not tables:
        st.info("Справочник пуст. Проверьте наличие JSON-файлов в папке src/atlas/data/")
        return

    meta = st.session_state.get("cluster_meta") or {}
    dump_label = meta.get("engine_release")
    default_label = dump_label if dump_label in _SCHEMA_OPTIONS else RELEASE_LABELS["7.3"]

    selected_label = st.segmented_control(
        "Схема:",
        _SCHEMA_OPTIONS,
        default=default_label,
        key="atlas_schema_release",
    )
    if selected_label not in _SCHEMA_OPTIONS:
        selected_label = default_label
    release_key = release_key_from_label(selected_label)

    changelog = load_changelog()
    intro = format_changelog_intro(changelog)
    if intro:
        st.markdown(intro)
    details = format_changelog_details(changelog)
    if details:
        with st.expander("Полный список изменений схемы", expanded=False):
            st.markdown(details)

    scoped: dict[str, dict] = {}
    for name, info in tables.items():
        if not table_visible_for_release(info, release_key):
            continue
        view = dict(info)
        view["fields_doc"] = visible_fields_doc(info, release_key)
        scoped[name] = view

    groups = sorted(set(t["group"] for t in scoped.values()))

    col_filter, col_search = st.columns([1, 3], vertical_alignment="bottom")

    with col_filter:
        selected_group = st.selectbox(
            "Группа:",
            ["Все группы"] + groups,
            key="atlas_group_filter",
        )

    with col_search:
        search_term = st.text_input(
            "Поиск (Таблица / Поле / Описание):",
            placeholder="Например: vds_static, cluster_id...",
            key="atlas_search",
        ).strip().lower()

    filtered_tables = {}
    for name, info in scoped.items():
        name_lower = name.lower()
        desc_lower = info.get("summary", "").lower() or info.get("description", "").lower()

        fields_doc = info.get("fields_doc", {})
        fields_str = " ".join(k.lower() for k in fields_doc) if fields_doc else ""

        matches_search = (
            not search_term
            or search_term in name_lower
            or search_term in desc_lower
            or search_term in fields_str
        )

        matches_group = selected_group == "Все группы" or info["group"] == selected_group

        if matches_search and matches_group:
            starts_with_query = name_lower.startswith(search_term) if search_term else False
            filtered_tables[name] = (info, starts_with_query)

    sorted_filtered = sorted(
        filtered_tables.items(),
        key=lambda item: (not item[1][1], item[0]),
    )

    st.markdown(f"**Найдено таблиц:** {len(sorted_filtered)}")
    st.divider()

    grouped = defaultdict(list)
    for name, (info, _) in sorted_filtered:
        grouped[info["group"]].append((name, info))

    display_groups = (
        [selected_group] if selected_group != "Все группы" else sorted(grouped.keys())
    )

    for group_name in display_groups:
        if group_name in grouped:
            render_group_section(group_name, grouped[group_name])

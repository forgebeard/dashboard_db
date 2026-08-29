"""Список дисков и образов: фильтры, сводка, таблица и текстовый инспектор."""

import streamlit as st

from core.constants import image_health_counts, image_status_tone
from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_health_filter,
    render_page_header,
    style_status_column,
)
from disks.disks_utils import (
    fetch_disks_data,
    prepare_disk_rows,
    process_disks_dataframe,
)

DISK_FILTER_DEFAULTS = {
    "disk_search_name": "",
    "disk_search_vm": "",
    "disk_search_sd": "",
    "disk_health_filter": "all",
}


def render_disks_list(active_db, cluster_meta):
    del cluster_meta
    header_box = st.container()
    show_clear = filters_are_active(DISK_FILTER_DEFAULTS)
    if show_clear:
        health_col, disk_col, vm_col, sd_col, clear_col = st.columns(
            [1.6, 1.1, 1.1, 1.1, 0.8], vertical_alignment="bottom"
        )
    else:
        health_col, disk_col, vm_col, sd_col = st.columns(
            [1.6, 1.2, 1.2, 1.2], vertical_alignment="bottom"
        )
        clear_col = None

    with disk_col:
        search_disk = st.text_input(
            "Поиск диска:",
            placeholder="Имя или UUID...",
            key="disk_search_name",
        )
    with vm_col:
        search_vm = st.text_input(
            "Поиск ВМ:",
            placeholder="Имя ВМ...",
            key="disk_search_vm",
        )
    with sd_col:
        search_sd = st.text_input(
            "Поиск хранилища:",
            placeholder="Имя домена...",
            key="disk_search_sd",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(DISK_FILTER_DEFAULTS, key="disk_clear_filters")

    raw_df = fetch_disks_data(active_db, (search_disk, search_vm, search_sd))
    if raw_df.empty:
        counts = image_health_counts([])
    else:
        counts = image_health_counts(prepare_disk_rows(raw_df)["_status_code"])

    health = "all"
    if not raw_df.empty:
        with health_col:
            health = render_health_filter(
                (
                    ("all", f"Все ({counts['total']})"),
                    ("ok", f"OK ({counts['ok']})"),
                    ("problems", f"Остальное ({counts['problems']})"),
                ),
                key="disk_health_filter",
            )

    display_df = (
        process_disks_dataframe(raw_df, health_filter=health)
        if not raw_df.empty
        else raw_df
    )

    with header_box:
        render_page_header(
            "Диски и образы",
            active_db,
            details=[f"{counts['total']} дисков"],
        )

    if raw_df.empty:
        st.info("Диски по заданным критериям не найдены.")
        return
    if display_df.empty:
        st.info("Нет дисков, соответствующих выбранному состоянию.")
        return

    event = st.dataframe(
        style_status_column(display_df, image_status_tone),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя диска": st.column_config.TextColumn(),
            "UUID диска": st.column_config.TextColumn(width=220),
            "Статус": st.column_config.TextColumn(width=90),
            "ВМ": st.column_config.TextColumn(),
            "Хранилище": st.column_config.TextColumn(width=120),
            "Вирт. размер": st.column_config.TextColumn(width=100),
            "Факт. размер": st.column_config.TextColumn(width=100),
            "_status_code": None,
            "_inspect_image_guid": None,
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected = display_df.iloc[idx]
        selected_uuid = selected["_inspect_image_guid"]
        st.markdown(f"#### 🔍 Инспектор диска: {selected['Имя диска']}")
        st.caption(f"Диск: `{selected['UUID диска']}` | ВМ: {selected['ВМ']}")
        with st.spinner("Генерация полного отчета DISK-Inspector..."):
            from disks.disks_inspector_sql import get_disk_inspector_report

            result = get_disk_inspector_report(active_db, selected_uuid)
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

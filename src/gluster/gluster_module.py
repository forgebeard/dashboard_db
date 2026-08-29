"""Список томов Gluster: фильтры, сводка, таблица и текстовый инспектор."""

import streamlit as st

from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_page_header,
    try_load,
)
from gluster.gluster_utils import fetch_gluster_volumes, process_gluster_dataframe

GLUSTER_FILTER_DEFAULTS = {
    "gluster_cluster_filter": "Все кластеры",
    "gluster_search": "",
}


def render_gluster_list(active_db: str, cluster_meta: dict) -> None:
    header_box = st.container()
    cluster_names = sorted(
        {str(v) for v in (cluster_meta or {}).get("clusters", {}).values()}
    )

    show_clear = filters_are_active(GLUSTER_FILTER_DEFAULTS)
    if show_clear:
        cl_col, search_col, clear_col = st.columns(
            [1.2, 2.4, 0.9], vertical_alignment="bottom"
        )
    else:
        cl_col, search_col = st.columns([1.2, 3.0], vertical_alignment="bottom")
        clear_col = None

    with cl_col:
        selected_cluster = st.selectbox(
            "Кластер:",
            ["Все кластеры"] + cluster_names,
            key="gluster_cluster_filter",
        )
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / UUID):",
            placeholder="Введите имя тома или UUID...",
            key="gluster_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(
                GLUSTER_FILTER_DEFAULTS, key="gluster_clear_filters"
            )

    raw_df = try_load(
        "томов Gluster", fetch_gluster_volumes, active_db, (selected_cluster, search_term)
    )
    if raw_df is None:
        return
    display_df = process_gluster_dataframe(raw_df) if not raw_df.empty else raw_df

    with header_box:
        render_page_header(
            "Gluster",
            active_db,
            details=[f"{len(raw_df)} томов"],
        )

    if raw_df.empty:
        st.info("Тома Gluster не найдены.")
        return
    if display_df.empty:
        st.info("Нет томов, соответствующих критериям.")
        return

    event = st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Имя тома": st.column_config.TextColumn(),
            "UUID": st.column_config.TextColumn(width=220),
            "Кластер": st.column_config.TextColumn(width=140),
            "Тип": st.column_config.TextColumn(width=110),
            "Статус": st.column_config.TextColumn(width=110),
            "Заполнен (%)": st.column_config.ProgressColumn(
                "Заполнен", min_value=0, max_value=100, format="%f%%"
            ),
        },
        height=dataframe_height(len(display_df)),
    )

    if event.selection.rows:
        idx = event.selection.rows[0]
        selected = display_df.iloc[idx]
        selected_vid = selected["UUID"]
        st.markdown(f"#### 🔍 Инспектор тома: {selected['Имя тома']}")
        st.caption(f"UUID: `{selected_vid}` | Кластер: {selected['Кластер']}")
        with st.spinner("Генерация полного отчета Volume-Inspector..."):
            from gluster.gluster_inspector_sql import get_gluster_volume_report

            result = get_gluster_volume_report(active_db, str(selected_vid))
        if "error" in result:
            st.error(result["error"])
        else:
            st.code(result["report_text"], language="text")

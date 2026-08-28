# src/users/users_module.py
"""Список пользователей: домены из БД, счётчики ролей, деталь по клику."""

import streamlit as st

from core.ui_utils import (
    dataframe_height,
    filters_are_active,
    render_clear_filters_button,
    render_page_header,
)
from users.users_utils import (
    fetch_user_domains,
    fetch_user_permissions,
    fetch_users_data,
    format_user_role_summary,
    process_user_dataframe,
    process_user_permissions_table,
)

USER_FILTER_DEFAULTS = {
    "user_domain_filter": "Все домены",
    "user_search": "",
}


def render_users_list(active_db: str, cluster_meta: dict) -> None:
    header_box = st.container()
    domains = fetch_user_domains(active_db)
    domain_options = ["Все домены"] + domains

    show_clear = filters_are_active(USER_FILTER_DEFAULTS)
    if show_clear:
        domain_col, search_col, clear_col = st.columns(
            [1.2, 2.4, 0.9], vertical_alignment="bottom"
        )
    else:
        domain_col, search_col = st.columns([1.2, 3.0], vertical_alignment="bottom")
        clear_col = None

    with domain_col:
        current = st.session_state.get("user_domain_filter", "Все домены")
        if current not in domain_options:
            st.session_state["user_domain_filter"] = "Все домены"
        selected_domain = st.selectbox(
            "Домен аутентификации:",
            domain_options,
            key="user_domain_filter",
        )
    with search_col:
        search_term = st.text_input(
            "Поиск (Имя / UUID):",
            placeholder="Введите имя или UUID...",
            key="user_search",
        )
    if clear_col is not None:
        with clear_col:
            render_clear_filters_button(USER_FILTER_DEFAULTS, key="user_clear_filters")

    raw_df = fetch_users_data(active_db, (selected_domain, search_term))

    with header_box:
        render_page_header(
            "Пользователи и права",
            active_db,
            details=[f"{len(raw_df)} пользователей"],
        )

    if raw_df.empty:
        st.info("Пользователи не найдены.")
        return

    display_df = process_user_dataframe(raw_df)
    if display_df.empty:
        st.info("Нет пользователей, соответствующих критериям.")
        return

    event = st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        height=dataframe_height(len(display_df)),
        column_config={
            "Имя": st.column_config.TextColumn(width="medium"),
            "UUID": st.column_config.TextColumn(width=220),
            "Домен": st.column_config.TextColumn(width=140),
            "Ролей": st.column_config.NumberColumn(width=80),
            "Прав": st.column_config.NumberColumn(width=80),
        },
    )

    if not event.selection.rows:
        return

    idx = event.selection.rows[0]
    selected = display_df.iloc[idx]
    st.markdown(f"#### {selected['Имя']}")
    st.caption(f"UUID: `{selected['UUID']}` | Домен: {selected['Домен']}")
    perms = fetch_user_permissions(active_db, str(selected["UUID"]))
    summary = format_user_role_summary(perms)
    if perms.empty:
        st.info(summary)
        return
    st.caption(summary.replace("\n", " · "))
    detail = process_user_permissions_table(perms)
    st.dataframe(
        detail,
        width="stretch",
        hide_index=True,
        height=dataframe_height(len(detail)),
    )

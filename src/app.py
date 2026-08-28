# src/app.py
"""Точка входа Streamlit: подключение к дампу и ленивый рендер одного раздела."""

import logging
import os
import sys
from pathlib import Path

import streamlit as st

# streamlit run src/app.py: корень пакетов — каталог src/
sys.path.append(os.path.dirname(__file__))


def _configure_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "app.log", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
        force=True,
    )


_configure_logging()

from core.config import APP_TITLE, APP_LAYOUT, FONT_SIZE_CSS
from core.db_utils import get_available_databases
from core.data_loader import load_cluster_metadata
from core.sql_editor import render_global_sql

from vms.vms_module import render_vms_list
from vms.vms_diagnostics import render_vms_diagnostics
from snapshots.snapshots_module import render_snapshots_list
from snapshots.snapshots_diagnostics import render_snapshots_diagnostics
from hosts.hosts_module import render_hosts_list
from hosts.hosts_diagnostics import render_hosts_diagnostics
from clusters.clusters_module import render_clusters_list
from clusters.clusters_diagnostics import render_clusters_diagnostics
from storage.storage_module import render_storage_list
from storage.storage_diagnostics import render_storage_diagnostics
from disks.disks_module import render_disks_list
from disks.disks_diagnostics import render_disks_diagnostics
from gluster.gluster_module import render_gluster_list
from gluster.gluster_diagnostics import render_gluster_diagnostics
from tasks.tasks_module import render_tasks_list
from tasks.tasks_diagnostics import render_tasks_diagnostics
from audit.audit_module import render_audit_log
from audit.audit_diagnostics import render_audit_diagnostics
from cert.certificates import render_certificates
from networks.network_module import render_networks_list
from system.system_module import render_system_list
from users.users_module import render_users_list
from users.users_diagnostics import render_users_diagnostics
from atlas.atlas_module import render_schema_atlas

# Разделы с собственным page header (фаза A).
_SHELL_SECTIONS = frozenset({"hosts", "vms", "clusters"})

SECTIONS: list[tuple[str, str, str]] = [
    ("hosts", "Хосты", ":material/dns:"),
    ("vms", "Виртуальные машины", ":material/computer:"),
    ("snapshots", "Снапшоты", ":material/photo_camera:"),
    ("clusters", "Кластеры", ":material/hub:"),
    ("networks", "Сети", ":material/lan:"),
    ("storage", "Хранилища", ":material/storage:"),
    ("disks", "Диски и образы", ":material/hard_drive:"),
    ("gluster", "Gluster", ":material/grid_view:"),
    ("tasks", "Задачи", ":material/pending_actions:"),
    ("audit", "Журнал событий", ":material/history:"),
    ("cert", "Сертификаты", ":material/key:"),
    ("system", "Системные", ":material/settings:"),
    ("users", "Пользователи и права", ":material/group:"),
    ("atlas", "Справочник", ":material/menu_book:"),
]
SECTION_LABELS = {item[0]: item[1] for item in SECTIONS}

NAV_GROUPS: dict[str, list[str]] = {
    "Инфраструктура": ["hosts", "vms", "snapshots", "clusters"],
    "Хранение и сеть": ["networks", "storage", "disks", "gluster"],
    "Операции": ["tasks", "audit"],
    "Система": ["cert", "system", "users"],
    "Справочник": ["atlas"],
}


def _render_section(section_id: str, db_name: str, cluster_meta: dict) -> None:
    """Вызывает UI только выбранного раздела (диагностика рядом, если есть)."""
    if section_id not in _SHELL_SECTIONS:
        st.subheader(SECTION_LABELS[section_id])

    if section_id == "hosts":
        render_hosts_list(db_name, cluster_meta)
        st.divider()
        render_hosts_diagnostics(db_name)
    elif section_id == "vms":
        render_vms_list(db_name, cluster_meta)
        st.divider()
        render_vms_diagnostics(db_name)
    elif section_id == "snapshots":
        render_snapshots_list(db_name, cluster_meta)
        st.divider()
        render_snapshots_diagnostics(db_name)
    elif section_id == "clusters":
        render_clusters_list(db_name, cluster_meta)
        st.divider()
        render_clusters_diagnostics(db_name)
    elif section_id == "networks":
        render_networks_list(db_name, cluster_meta)
    elif section_id == "storage":
        render_storage_list(db_name, cluster_meta)
        st.divider()
        render_storage_diagnostics(db_name)
    elif section_id == "disks":
        render_disks_list(db_name, cluster_meta)
        st.divider()
        render_disks_diagnostics(db_name)
    elif section_id == "gluster":
        render_gluster_list(db_name, cluster_meta)
        st.divider()
        render_gluster_diagnostics(db_name)
    elif section_id == "tasks":
        render_tasks_list(db_name, cluster_meta)
        st.divider()
        render_tasks_diagnostics(db_name)
    elif section_id == "audit":
        render_audit_log(db_name, cluster_meta)
        st.divider()
        render_audit_diagnostics(db_name)
    elif section_id == "cert":
        render_certificates(db_name)
    elif section_id == "system":
        render_system_list(db_name, cluster_meta)
    elif section_id == "users":
        render_users_list(db_name, cluster_meta)
        st.divider()
        render_users_diagnostics(db_name)
    elif section_id == "atlas":
        render_schema_atlas()


def _make_section_page(section_id: str, icon: str):
    def _page() -> None:
        st.session_state["section"] = section_id
        db_name = st.session_state.get("active_db")
        if not db_name:
            st.error("База данных не выбрана.")
            return
        try:
            _render_section(
                section_id,
                db_name,
                st.session_state.get("cluster_meta", {}),
            )
        except Exception as exc:
            st.error(f"Ошибка при отрисовке раздела «{SECTION_LABELS[section_id]}»: {exc}")
            st.exception(exc)

    _page.__name__ = f"page_{section_id}"
    _page.__qualname__ = f"page_{section_id}"
    return st.Page(
        _page,
        title=SECTION_LABELS[section_id],
        icon=icon,
        url_path=section_id,
        default=section_id == "hosts",
    )


st.set_page_config(page_title=APP_TITLE, layout=APP_LAYOUT)

st.markdown(
    f"""
    <style>
        .stDataFrame td {{ white-space: nowrap; }}
        .stDataFrame {{ font-size: {FONT_SIZE_CSS} !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.header(":material/settings: Подключение")

available_dbs = get_available_databases()
if not available_dbs:
    st.error("Не удалось получить список баз. Проверьте DB_* в .env и доступность PostgreSQL.")
    st.stop()

selected_db = st.sidebar.radio(
    "База для анализа",
    options=available_dbs,
    index=0,
    key="db_selector",
)

if st.session_state.get("active_db") != selected_db:
    st.session_state["active_db"] = selected_db
    if "cluster_meta" in st.session_state:
        del st.session_state["cluster_meta"]
    with st.spinner(f"Загрузка структуры {selected_db}..."):
        st.session_state["cluster_meta"] = load_cluster_metadata(selected_db)

active_display_db = st.session_state.get("active_db", selected_db)
st.sidebar.markdown(f"Текущая БД: `{active_display_db}`")
st.sidebar.caption("READ ONLY")

icon_by_id = {item[0]: item[2] for item in SECTIONS}
nav_spec = {
    group: [_make_section_page(section_id, icon_by_id[section_id]) for section_id in ids]
    for group, ids in NAV_GROUPS.items()
}
page = st.navigation(nav_spec, position="sidebar")

with st.expander("SQL-редактор", expanded=False):
    render_global_sql(active_display_db)

page.run()

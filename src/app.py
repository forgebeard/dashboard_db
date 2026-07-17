# src/app.py
"""
Главный файл приложения Streamlit (Точка входа).

Отвечает за:
- Инициализацию конфигурации страницы и CSS-стилей.
- Управление сессией пользователя и переключение между базами данных.
- Маршрутизацию вызовов к функциональным модулям (Хосты, ВМ, Снапшоты и др.).
- Отображение глобального SQL-редактора для произвольных запросов.
"""

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Фреймворк для построения веб-интерфейса дашборда

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения и путям файловой системы
import sys              # Управление путями поиска модулей (sys.path)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА: КОНФИГУРАЦИЯ И УТИЛИТЫ (CORE) ---
sys.path.append(os.path.dirname(__file__))  # Добавляем корень src/ в путь поиска
from core.config import APP_TITLE, APP_LAYOUT, FONT_SIZE_CSS  # Глобальные настройки UI и стилей
from core.db_utils import get_available_databases, get_sqlalchemy_engine  # Поиск дампов и подключение к БД
from core.data_loader import load_cluster_metadata  # Загрузка справочников инфраструктуры (ДЦ, Кластеры, Хосты)
from core.sql_editor import render_global_sql       # Компонент глобального SQL-редактора

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА: ФУНКЦИОНАЛЬНЫЕ РАЗДЕЛЫ ---
from vms.vms_module import render_vms_list                 # UI списка виртуальных машин
from vms.vms_diagnostics import render_vms_diagnostics     # Диагностика таблиц ВМ
from snapshots.snapshots_module import render_snapshots_list           # UI списка снапшотов
from snapshots.snapshots_diagnostics import render_snapshots_diagnostics  # Диагностика таблиц снапшотов
from hosts.hosts_module import render_hosts_list           # UI списка хостов
from hosts.hosts_diagnostics import render_hosts_diagnostics  # Диагностика таблиц хостов
from clusters.clusters_module import render_clusters_list  # UI списка кластеров
from clusters.clusters_diagnostics import render_clusters_diagnostics  # Диагностика таблиц кластеров
from storage.storage_module import render_storage_list     # UI списка хранилищ
from storage.storage_diagnostics import render_storage_diagnostics  # Диагностика таблиц хранения
from disks.disks_module import render_disks_list           # UI списка дисков и образов
from disks.disks_diagnostics import render_disks_diagnostics  # Диагностика таблиц дисков
from gluster.gluster_module import render_gluster_list     # UI списка томов Gluster
from gluster.gluster_diagnostics import render_gluster_diagnostics  # Диагностика таблиц Gluster
from tasks.tasks_module import render_tasks_list           # UI списка асинхронных задач VDSM
from tasks.tasks_diagnostics import render_tasks_diagnostics  # Диагностика таблиц задач
from audit.audit_module import render_audit_log            # UI журнала событий
from audit.audit_diagnostics import render_audit_diagnostics  # Диагностика таблиц аудита
from cert.certificates import render_certificates          # UI сертификатов PKI
from networks.network_module import render_networks_list   # UI логических сетей
from system.system_module import render_system_list        # UI системных таблиц
from users.users_module import render_users_list           # UI списка пользователей
from users.users_diagnostics import render_users_diagnostics  # Диагностика таблиц пользователей и прав
from atlas.atlas_module import render_schema_atlas         # Интерактивный справочник схемы БД

# ==============================================================================
# ИНИЦИАЛИЗАЦИЯ ИНТЕРФЕЙСА
# ==============================================================================

# Настройка заголовка вкладки браузера и ширины контента
st.set_page_config(page_title=APP_TITLE, layout=APP_LAYOUT)

# Внедрение глобальных CSS-стилей для таблиц (неразрывные строки, размер шрифта)
st.markdown(f"""
    <style>
        .stDataFrame td {{ white-space: nowrap; }} 
        .stDataFrame {{ font-size: {FONT_SIZE_CSS} !important; }} 
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# САЙДБАР: УПРАВЛЕНИЕ ПОДКЛЮЧЕНИЕМ
# ==============================================================================

st.sidebar.header("⚙️ Управление подключением")

# Выбор базы данных из автоматически найденных локальных дампов
available_dbs = get_available_databases()
selected_db = st.sidebar.radio(
    "Выберите базу для анализа:",
    options=available_dbs,
    index=0,
    key="db_selector"
)

# Логика переключения активной БД и обновления кэша метаданных
if st.session_state.get('active_db') != selected_db:
    st.session_state['active_db'] = selected_db
    
    # Принудительная очистка кэша при смене источника данных
    if 'cluster_meta' in st.session_state:
        del st.session_state['cluster_meta']
        
    with st.spinner(f"Загрузка структуры {selected_db}..."):
        st.session_state['cluster_meta'] = load_cluster_metadata(selected_db)

# Получение текущего активного идентификатора БД
active_display_db = st.session_state.get('active_db', selected_db)
st.sidebar.markdown(f"**Текущая БД:** `{active_display_db}`")

# Виджет статуса инфраструктуры (количество объектов в выбранном дампе)
meta = st.session_state.get('cluster_meta', {})
if meta:
    with st.sidebar.expander("Инфраструктура", expanded=True):
        st.markdown(f"Хостов: **{len(meta.get('hosts', {}))}**")
        st.markdown(f"Кластеров: **{len(meta.get('clusters', {}))}**")
        st.markdown(f"СХД: **{len(meta.get('storage_domains', {}))}**")
        st.markdown(f"Дата-центров: **{len(meta.get('datacenters', {}))}**")

# ==============================================================================
# ГЛОБАЛЬНЫЙ SQL-РЕДАКТОР
# ==============================================================================
render_global_sql(active_display_db)

# ==============================================================================
# МАРШРУТИЗАЦИЯ ВКЛАДОК
# ==============================================================================

# Определение порядка и типов вкладок
tab_definitions = [
    {"title": "🖥️ Хосты", "type": "module_host"},
    {"title": "💻 Виртуальные машины", "type": "module_vm"},
    {"title": "📸 Снапшоты", "type": "module_snapshot"},
    {"title": "🏢 Кластеры", "type": "module_cluster"},
    {"title": "🌐 Сети", "type": "module_network"},
    {"title": "💾 Хранилища", "type": "module_storage"},
    {"title": "💿 Диски и Образы", "type": "module_disks"},
    {"title": "🧱 Gluster", "type": "module_gluster"},
    {"title": "⚡ Задачи", "type": "module_tasks"},
    {"title": "📜 Журнал событий", "type": "module_audit"},
    {"title": "🔒 Сертификаты", "type": "module_cert"},
    {"title": "🛠️ Системные", "type": "module_system"},
    {"title": "👤 Пользователи и права", "type": "module_users"},
    {"title": "📚 Справочник", "type": "module_atlas"},
]

tabs = st.tabs([t["title"] for t in tab_definitions])

# Отрисовка содержимого каждой вкладки
for i, tab in enumerate(tabs):
    with tab:
        tab_def = tab_definitions[i]
        
        if not active_display_db:
            st.error("База данных не выбрана.")
            continue
            
        try:
            # Вызов соответствующего модуля в зависимости от типа вкладки
            if tab_def["type"] == "module_host":
                render_hosts_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_hosts_diagnostics(active_display_db)
                
            elif tab_def["type"] == "module_vm":
                render_vms_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_vms_diagnostics(active_display_db)

            elif tab_def["type"] == "module_snapshot":
                render_snapshots_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_snapshots_diagnostics(active_display_db)

            elif tab_def["type"] == "module_cluster":
                render_clusters_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_clusters_diagnostics(active_display_db)

            elif tab_def["type"] == "module_network":
                render_networks_list(active_display_db, st.session_state.get('cluster_meta', {}))
                
            elif tab_def["type"] == "module_storage":
                render_storage_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_storage_diagnostics(active_display_db)

            elif tab_def["type"] == "module_disks":
                render_disks_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_disks_diagnostics(active_display_db)

            elif tab_def["type"] == "module_gluster":
                render_gluster_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_gluster_diagnostics(active_display_db)
                
            elif tab_def["type"] == "module_tasks":
                render_tasks_list(active_display_db)
                st.divider()
                render_tasks_diagnostics(active_display_db)
                
            elif tab_def["type"] == "module_audit":
                render_audit_log(active_display_db)
                st.divider()
                render_audit_diagnostics(active_display_db)
                
            elif tab_def["type"] == "module_cert":
                render_certificates(active_display_db)

            elif tab_def["type"] == "module_system":
                render_system_list(active_display_db, st.session_state.get('cluster_meta', {}))

            elif tab_def["type"] == "module_users":
                render_users_list(active_display_db, st.session_state.get('cluster_meta', {}))
                st.divider()
                render_users_diagnostics(active_display_db)

            elif tab_def["type"] == "module_atlas":
                # Справочник работает автономно и не требует cluster_meta
                render_schema_atlas()
                
        except Exception as e:
            # Перехват критических ошибок рендеринга раздела
            st.error(f"Ошибка при отрисовке раздела '{tab_def['title']}': {e}")
            st.exception(e)
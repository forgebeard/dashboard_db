"""Диагностика раздела «Хранилища»."""

from core.table_preview import render_grouped_table_preview

STORAGE_TABLES = {
    "Core Storage": {
        "storage_domain_static": "Статические параметры доменов хранения",
        "storage_domain_dynamic": "Динамический статус доменов хранения",
        "storage_pool": "Пулы хранения (Data Centers)",
        "storage_domain_shared_status": "Общий статус доменов",
    },
    "Block Devices (LUN/iSCSI)": {
        "luns": "LUNы (блочные устройства)",
        "storage_server_connections": "Подключения к серверам хранения",
        "lun_storage_server_connection_map": "Связь LUN с подключениями",
    },
    "Advanced": {
        "iscsi_bonds": "iSCSI бонды (агрегация)",
        "cinder_storage": "Интеграция с OpenStack Cinder",
        "unregistered_disks": "Незарегистрированные диски",
        "external_leases": "Внешние аренды (блокировки)",
    },
    "Backup & Infra": {
        "infrastructure_backup": "Резервные копии инфраструктуры Engine",
        "infrastructure_backup_file_map": "Файлы копий инфраструктуры",
        "infrastructure_backups": "Снятые копии инфраструктуры",
        "infrastructure_backup_plans": "Планы копий инфраструктуры",
        "infrastructure_backup_storages": "Цели хранения копий инфраструктуры",
        "infrastructure_backup_plan_storage_map": "Связь планов и целей хранения",
    },
}


def render_storage_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        STORAGE_TABLES,
        title="Таблицы раздела «Хранилища»",
        limit_key=f"storage_limit_{active_db}",
    )

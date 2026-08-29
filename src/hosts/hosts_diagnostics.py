"""Диагностика раздела «Хосты»: сырые таблицы vds_*/host_*."""

from core.table_preview import render_grouped_table_preview

HOST_TABLES = {
    "Core": {
        "vds_static": "Статические параметры хоста",
        "vds_dynamic": "Динамический статус хоста",
        "vds_statistics": "Статистика хоста за период",
    },
    "Network": {
        "vds_interface": "Сетевые интерфейсы хоста",
        "vds_interface_statistics": "Статистика сетевых интерфейсов",
        "host_nic_vfs_config": "Конфигурация SR-IOV VFS",
    },
    "Hardware & Config": {
        "vds_kdump_status": "Статус kdump на хосте",
        "vds_spm_id_map": "Маппинг SPM",
        "host_device": "Физические устройства хоста (PCI, USB)",
        "host_template": "Шаблон установки хоста",
    },
}


def render_hosts_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        HOST_TABLES,
        title="Таблицы раздела «Хосты»",
        limit_key=f"host_limit_{active_db}",
    )

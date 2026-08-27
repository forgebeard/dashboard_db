"""Диагностика раздела «Виртуальные машины»."""

from core.table_preview import render_grouped_table_preview

VM_TABLES = {
    "Core": {
        "vm_static": "Статические параметры ВМ",
        "vm_dynamic": "Динамический статус ВМ",
        "vm_statistics": "Статистика ВМ за период",
    },
    "Storage": {
        "vm_device": "Устройства ВМ (диски, NIC)",
        "vm_backup_disk_map": "Карта дисков для бэкапов",
        "vm_backups": "Резервные копии ВМ",
        "vm_checkpoint_disk_map": "Карта дисков для чекпоинтов",
        "vm_checkpoints": "Чекпоинты ВМ",
        "vm_ovf_generations": "Версии OVF-конфигурации",
    },
    "Network": {
        "vm_interface": "Сетевые интерфейсы ВМ",
        "vm_interface_statistics": "Статистика сетевых интерфейсов",
        "vm_interface_filter_parameters": "Параметры фильтрации трафика",
        "vm_guest_agent_interfaces": "Интерфейсы от guest agent",
    },
    "Config": {
        "vm_init": "Параметры cloud-init/sysprep",
        "vm_external_data": "Внешние метаданные ВМ",
        "vm_host_pinning_map": "Привязка ВМ к хостам",
        "vm_vds_numa_node_map": "NUMA-топология ВМ",
        "vm_pool_map": "Связь ВМ с пулами",
        "vm_pools": "Группы/пулы ВМ",
        "vm_groups": "Логические группы ВМ",
        "vm_jobs": "Специализированные задачи ВМ",
        "vm_icon_defaults": "Иконки ВМ по умолчанию",
        "vm_icons": "Пользовательские иконки ВМ",
        "vm_nvram_data": "Данные NVRAM (UEFI)",
    },
}


def render_vms_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        VM_TABLES,
        title="Таблицы раздела «Виртуальные машины»",
        limit_key=f"vm_limit_{active_db}",
    )

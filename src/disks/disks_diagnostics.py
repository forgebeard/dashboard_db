"""Диагностика раздела «Диски и образы»."""

from core.table_preview import render_grouped_table_preview

DISKS_TABLES = {
    "Core Disks": {
        "base_disks": "Базовая информация о логических дисках",
        "disk_image_dynamic": "Динамические параметры образов (фактический размер)",
        "images": "Образы дисков (слои/снапшоты)",
    },
    "Mappings & Relations": {
        "image_storage_domain_map": "Привязка образов к доменам хранения",
        "disk_lun_map": "Маппинг дисков к LUN (для блочных хранилищ)",
        "vm_device": "Привязка устройств (дисков) к ВМ",
    },
}


def render_disks_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        DISKS_TABLES,
        title="Таблицы раздела «Диски и образы»",
        limit_key=f"disks_limit_{active_db}",
    )

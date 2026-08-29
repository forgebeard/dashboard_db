"""Диагностика раздела «Снапшоты и слои»."""

from core.table_preview import render_grouped_table_preview

SNAPSHOT_TABLES = {
    "Metadata": {
        "snapshots": "Метаданные снапшотов ВМ",
        "vm_checkpoints": "Чекпоинты (Live Snapshots)",
    },
    "DiskStatus": {
        "images": "Образы дисков и статусы",
        "image_storage_domain_map": "Привязка образов к хранилищам",
    },
}


def render_snapshots_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        SNAPSHOT_TABLES,
        title="Таблицы раздела «Снапшоты и слои»",
        limit_key=f"snap_limit_{active_db}",
    )

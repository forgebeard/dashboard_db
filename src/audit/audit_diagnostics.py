"""Диагностика журнала событий."""

from core.table_preview import render_grouped_table_preview

AUDIT_TABLES = {
    "": {
        "audit_log": "Основной журнал событий (аудит действий)",
        "vdc_db_log": "Лог внутренних ошибок БД движка oVirt",
        "sp_events": "Служебные события Engine",
    }
}


def render_audit_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        AUDIT_TABLES,
        title="Таблицы журнала событий",
        limit_key=f"audit_diag_limit_{active_db}",
        order_overrides={"vdc_db_log": "occured_at"},
    )

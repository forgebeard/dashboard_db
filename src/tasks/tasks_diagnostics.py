"""Диагностика раздела «Задачи»."""

from core.table_preview import render_grouped_table_preview

TASK_TABLES = {
    "Core": {
        "job": "Родительские задачи и операции",
        "step": "Шаги выполнения операций",
        "vm_jobs": "Специфичные задачи ВМ",
    },
    "Async VDSM": {
        "async_tasks": "Асинхронные задачи VDSM",
        "command_entities": "История команд и контекст (параметры)",
    },
    "Relations": {
        "async_tasks_entities": "Привязка async-задач к сущностям",
        "job_subject_entity": "Связи задач с сущностями",
        "step_subject_entity": "Связи шагов с сущностями",
        "command_assoc_entities": "Связи команд с сущностями",
    },
    "Audit & Events": {
        "audit_log": "Аудит-лог событий",
        "event_map": "Карта событий",
        "event_notification_hist": "История уведомлений",
        "event_subscriber": "Подписчики событий",
        "dwh_history_timekeeping": "Отслеживание времени для DWH",
    },
}


def render_tasks_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        TASK_TABLES,
        title="Таблицы раздела «Задачи»",
        limit_key=f"task_limit_{active_db}",
    )

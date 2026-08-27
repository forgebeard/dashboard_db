"""Диагностика раздела «Gluster»."""

from core.table_preview import render_grouped_table_preview

GLUSTER_TABLES = {
    "Тома и кирпичи": {
        "gluster_volumes": "Тома Gluster",
        "gluster_volume_details": "Детали томов (статистика)",
        "gluster_volume_bricks": "Кирпичи томов",
        "gluster_volume_brick_details": "Детали кирпичей",
        "gluster_volume_options": "Опции томов",
        "gluster_global_volume_options": "Глобальные опции",
        "gluster_volume_access_protocols": "Протоколы доступа",
        "gluster_volume_transport_types": "Типы транспорта",
    },
    "Geo-replication": {
        "gluster_georep_session": "Сессии гео-репликации",
        "gluster_georep_session_details": "Детали синхронизации",
        "gluster_georep_config": "Конфигурация geo-rep",
    },
    "Сервисы и хуки": {
        "gluster_services": "Сервисы Gluster",
        "gluster_service_types": "Типы сервисов",
        "gluster_cluster_services": "Сервисы кластера",
        "gluster_server": "Серверы Gluster",
        "gluster_server_services": "Сервисы на серверах",
        "gluster_hooks": "Хуки кластера",
        "gluster_server_hooks": "Хуки серверов",
    },
    "Планировщик и снапшоты": {
        "gluster_volume_snapshots": "Снапшоты томов",
        "gluster_volume_snapshot_config": "Конфиг снапшотов",
        "gluster_volume_snapshot_schedules": "Расписание снапшотов",
        "gluster_scheduler_job_details": "Задачи планировщика",
        "gluster_scheduler_job_params": "Параметры задач",
    },
    "Конфигурация": {
        "gluster_config_master": "Master конфигурация",
    },
}


def render_gluster_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        GLUSTER_TABLES,
        title="Таблицы раздела «Gluster»",
        limit_key=f"gluster_limit_{active_db}",
    )

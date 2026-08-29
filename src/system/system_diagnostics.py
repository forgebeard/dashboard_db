"""Диагностика системных таблиц oVirt Engine."""

from core.table_preview import render_grouped_table_preview

SYSTEM_TABLES = {
    "Config": {
        "schema_version": "Версия схемы БД",
        "vdc_options": "Опции движка oVirt",
        "external_variable": "Внешние переменные",
    },
    "Security": {
        "engine_sessions": "Активные сессии движка",
        "fence_agents": "Агенты фенсинга (IPMI)",
        "libvirt_secrets": "Секреты libvirt",
        "certificates_data": "Данные сертификатов PKI",
    },
    "Resources & Quotas": {
        "quota": "Квоты ресурсов",
        "quota_limitation": "Ограничения квот",
        "qos": "Параметры QoS",
    },
    "Integrations": {
        "providers": "Внешние провайдеры",
        "provider_binding_host_id": "Привязка провайдеров к хостам",
        "image_transfers": "Передачи образов",
    },
    "Audit": {
        "vdc_db_log": "Лог ошибок БД",
        "business_entity_snapshot": "Снапшоты бизнес-сущностей",
        "custom_actions": "Пользовательские действия",
        "dwh_osinfo": "OS-информация для DWH",
    },
    "Internal & Utils": {
        "object_column_white_list": "Белый список колонок объектов",
        "object_column_white_list_sql": "SQL белый список колонок",
    },
}

_MASK = {
    "fence_agents": ["agent_password"],
    "providers": ["auth_password"],
    "libvirt_secrets": ["secret_value"],
    "engine_sessions": ["user_id", "source_ip"],
}


def render_system_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        SYSTEM_TABLES,
        title="Системные таблицы",
        limit_key=f"sys_limit_{active_db}",
        row_limit_overrides={"vdc_db_log": 50},
        mask_columns=_MASK,
    )

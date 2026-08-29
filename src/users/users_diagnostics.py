"""Диагностика раздела «Пользователи и права»."""

from core.table_preview import render_grouped_table_preview

USERS_TABLES = {
    "Auth & Profiles": {
        "users": "Пользователи системы",
        "user_profiles": "Свойства профилей (EAV/JSONB)",
    },
    "Roles & Permissions": {
        "roles": "Роли доступа",
        "permissions": "Назначенные права на объекты",
        "roles_groups": "Связь ролей с группами действий",
        "ad_groups": "Группы Active Directory",
    },
    "Tags & Labels": {
        "tags": "Теги объектов",
        "tags_user_map": "Теги пользователей",
        "tags_user_group_map": "Теги групп пользователей",
        "tags_vm_map": "Теги ВМ",
        "tags_vm_pool_map": "Теги пулов ВМ",
        "tags_vds_map": "Теги хостов",
        "labels": "Метки сетей/интерфейсов",
        "labels_map": "Маппинг меток",
        "vfs_config_labels": "Метки в VFS конфигурации",
    },
    "SSO & Bookmarks": {
        "sso_clients": "SSO клиенты",
        "sso_scope_dependency": "Зависимости scopes SSO",
        "bookmarks": "Закладки пользователей",
    },
}


def render_users_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        USERS_TABLES,
        title="Таблицы раздела «Пользователи и права»",
        limit_key=f"users_limit_{active_db}",
        json_text_columns={"user_profiles": ["property_content"]},
    )

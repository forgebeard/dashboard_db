"""Диагностика раздела «Сети»."""

from core.table_preview import render_grouped_table_preview

NETWORK_TABLES = {
    "Core": {
        "network": "Логические сети (VLAN, подсети, шлюзы)",
        "network_cluster": "Привязка сетей к кластерам и политики",
        "vnic_profiles": "Профили vNIC (QoS, фильтры)",
    },
    "Physical": {
        "network_attachments": "Подключения сетей к интерфейсам хостов/ВМ",
        "vds_interface": "Физические интерфейсы хостов (связь по имени)",
    },
    "Config": {
        "dns_resolver_configuration": "Конфигурации DNS-резолверов",
        "name_server": "Список DNS-серверов",
        "mac_pools": "Пулы MAC-адресов",
        "mac_pool_ranges": "Диапазоны MAC-адресов в пулах",
        "vfs_config_networks": "Сети в конфигурации VFS",
        "network_filter": "Фильтры трафика libvirt (nwfilter rules)",
    },
}


def render_networks_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        NETWORK_TABLES,
        title="Таблицы раздела «Сети»",
        limit_key=f"net_limit_{active_db}",
    )

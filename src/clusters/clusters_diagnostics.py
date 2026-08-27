"""Диагностика раздела «Кластеры»."""

from core.table_preview import render_grouped_table_preview

CLUSTER_TABLES = {
    "Core": {
        "cluster": "Основные параметры кластера",
        "cluster_features": "Справочник функций кластера",
        "supported_cluster_features": "Функции, поддерживаемые конкретным кластером",
        "supported_host_features": "Функции, поддерживаемые конкретным хостом (CPU flags)",
        "cpu_profiles": "Профили CPU",
    },
    "Policies": {
        "cluster_policies": "Политики планирования ресурсов",
        "cluster_policy_units": "Единицы (фильтры/веса) политик",
        "policy_units": "Глобальный справочник единиц политик",
    },
    "Affinity": {
        "affinity_groups": "Группы аффинности (притяжение/отталкивание)",
        "affinity_group_members": "Члены групп аффинности (ВМ/Хосты)",
    },
    "NUMA": {
        "numa_node": "NUMA-узлы хостов и ВМ",
        "numa_node_cpu_map": "Маппинг физических CPU-ядер к NUMA-узлам",
    },
}


def render_clusters_diagnostics(active_db: str) -> None:
    render_grouped_table_preview(
        active_db,
        CLUSTER_TABLES,
        title="Таблицы раздела «Кластеры»",
        limit_key=f"cluster_limit_{active_db}",
    )

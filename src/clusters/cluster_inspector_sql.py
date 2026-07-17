# src/clusters/cluster_inspector_sql.py
"""
Модуль генерации диагностического отчета по кластеру (Cluster-Inspector).
Использует прямое подключение psycopg2 для сложных выборок.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (DB_USER, DB_PASSWORD и др.)
from datetime import datetime  # Работа с датой/временем для форматирования
import html             # Экранирование спецсимволов для безопасности отчета
import json             # Парсинг cluster_policy_custom_properties

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL для прямого подключения к БД
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.constants import HOST_STATUS_MAP  # Глобальный справочник статусов хостов


def _safe_text(value: str | None) -> str:
    """Экранирует HTML-спецсимволы для безопасного вывода в отчете."""
    if value is None:
        return "—"
    return html.escape(str(value))


def _fmt_size(mb: int | None) -> str:
    """Форматирует размер из МБ в ГБ."""
    if not mb:
        return "—"
    return f"{round(mb / 1024, 1)} ГБ"


def _safe_date(dt):
    """Приводит дату к naive-формату без tzinfo."""
    if not dt:
        return None
    return dt.replace(tzinfo=None) if hasattr(dt, 'replace') else dt


def _fmt_date(dt) -> str:
    """Форматирует дату в читаемый вид."""
    if not dt:
        return "—"
    return _safe_date(dt).strftime('%d.%m.%Y %H:%M:%S')


# Маппинг архитектуры кластера (из confirmed schema)
ARCHITECTURE_MAP = {
    1: "x86_64",
}


def get_cluster_inspector_report(db_name: str, cluster_id: str) -> dict:
    """
    Возвращает словарь с текстовым отчетом и навигационными данными по кластеру.
    
    Args:
        db_name: Имя базы данных (дампа)
        cluster_id: UUID кластера
        
    Returns:
        Словарь с ключами: report_text, nav_data, error (при неудаче)
    """
    cluster_search = str(cluster_id).strip().lower()
    
    conn_params = {
        "dbname": db_name,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    try:
        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                now_naive = datetime.now().replace(tzinfo=None)

                # 1. Основная информация о кластере
                cur.execute("""
                    SELECT c.*, sp.name AS datacenter_name
                    FROM cluster c
                    LEFT JOIN storage_pool sp ON c.storage_pool_id = sp.id
                    WHERE c.cluster_id::text = %s LIMIT 1
                """, (cluster_search,))
                
                cluster = cur.fetchone()
                if not cluster:
                    return {"error": "Кластер не найден.", "report_text": "", "nav_data": {}}

                arch_label = ARCHITECTURE_MAP.get(
                    cluster['architecture'], 
                    f"Code {cluster['architecture']}"
                )

                report_lines = [
                    "═" * 78,
                    f"  Cluster-Inspector — Диагностический отчёт",
                    f"  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}",
                    "═" * 78,
                    "",
                    "ОСНОВНАЯ ИНФОРМАЦИЯ",
                    "─" * 78,
                    f"  Имя кластера:   {_safe_text(cluster['name'])}",
                    f"  UUID:           {cluster['cluster_id']}",
                    f"  Дата-центр:     {_safe_text(cluster['datacenter_name'])}",
                    f"  Совместимость:  {cluster['compatibility_version']}",
                    f"  Архитектура:    {arch_label}",
                    "",
                    "  Настройки:",
                    f"    Balloon:      {'Вкл' if cluster['enable_balloon'] else 'Выкл'}",
                    f"    KSM:          {'Вкл' if cluster['enable_ksm'] else 'Выкл'}",
                    f"    Fencing:      {'Вкл' if cluster['fencing_enabled'] else 'Выкл'}",
                    f"    HA Reserve:   {'Вкл' if cluster['ha_reservation'] else 'Выкл'}",
                ]

                # 2. Политики планирования (парсинг JSON-text)
                report_lines.append("\nПОЛИТИКИ ПЛАНИРОВАНИЯ")
                report_lines.append("─" * 78)
                
                custom_props = cluster.get('cluster_policy_custom_properties')
                if custom_props:
                    try:
                        props = json.loads(custom_props)
                        for key, value in sorted(props.items()):
                            report_lines.append(f"    {key:<35}: {value}")
                    except (json.JSONDecodeError, TypeError):
                        report_lines.append(f"    Ошибка парсинга: {_safe_text(custom_props[:100])}")
                else:
                    report_lines.append("    Пользовательские параметры не заданы.")

                # 3. Состав хостов (через view vds)
                cur.execute("""
                    SELECT v.vds_id::text, v.vds_name, v.status AS host_status_code,
                           v.physical_mem_mb, v.cpu_cores, v.cpu_sockets, v.cpu_threads,
                           v.usage_cpu_percent, v.usage_mem_percent
                    FROM vds v
                    WHERE v.cluster_id::text = %s
                    ORDER BY v.vds_name
                """, (cluster_search,))
                
                hosts = cur.fetchall()
                
                report_lines.append(f"\nХОСТЫ ({len(hosts)})")
                report_lines.append("─" * 78)
                
                if not hosts:
                    report_lines.append("    Хосты не обнаружены.")
                else:
                    report_lines.append(
                        f"    {'Имя хоста':<35} │ {'Статус':<15} │ "
                        f"{'Память':<12} │ {'CPU':<10} │ {'Загрузка CPU/MEM'}"
                    )
                    report_lines.append(
                        f"    {'─'*35}┼{'─'*17}┼{'─'*14}{'─'*12}┼{'─'*20}"
                    )
                    
                    for h in hosts:
                        status_label = HOST_STATUS_MAP.get(
                            h['host_status_code'], 
                            f"Code {h['host_status_code']}"
                        )
                        cpu_str = f"{h['cpu_cores']}C/{h['cpu_sockets']}S/{h['cpu_threads']}T"
                        load_str = f"{h['usage_cpu_percent'] or 0}%/{h['usage_mem_percent'] or 0}%"
                        
                        report_lines.append(
                            f"    {_safe_text(h['vds_name']):<35} │ {status_label:<15} │ "
                            f"{_fmt_size(h['physical_mem_mb']):<12} │ {cpu_str:<10} │ {load_str}"
                        )

                # 4. Группы аффинности
                cur.execute("""
                    SELECT ag.name, ag.vm_positive, ag.vm_enforcing,
                           ag.vds_positive, ag.vds_enforcing,
                           agm.vm_id::text, agm.vds_id::text
                    FROM affinity_groups ag
                    LEFT JOIN affinity_group_members agm ON ag.id = agm.affinity_group_id
                    WHERE ag.cluster_id::text = %s
                    ORDER BY ag.name
                """, (cluster_search,))
                
                aff_groups = cur.fetchall()
                
                report_lines.append("\nГРУППЫ АФФИННОСТИ")
                report_lines.append("─" * 78)
                
                if not aff_groups:
                    report_lines.append("    Группы аффинности не настроены.")
                else:
                    current_group = None
                    for ag in aff_groups:
                        if ag['name'] != current_group:
                            current_group = ag['name']
                            vm_type = "Positive" if ag['vm_positive'] else "Negative"
                            vds_type = "Positive" if ag['vds_positive'] else "Negative"
                            enforcing = "Enforced" if ag['vm_enforcing'] else "Soft"
                            
                            report_lines.append(f"\n   📌 {_safe_text(current_group)}")
                            report_lines.append(
                                f"    VM Affinity: {vm_type} ({enforcing}) | "
                                f"Host Affinity: {vds_type}"
                            )
                            report_lines.append(f"    Члены:")
                        
                        member_info = []
                        if ag['vm_id']:
                            member_info.append(f"VM: {ag['vm_id'][:8]}...")
                        if ag['vds_id']:
                            member_info.append(f"Host: {ag['vds_id'][:8]}...")
                        
                        if member_info:
                            report_lines.append(f"      • {', '.join(member_info)}")

                # 5. NUMA-топология (АГРЕГИРОВАННАЯ СВОДКА)
                host_ids = [h['vds_id'] for h in hosts if h['vds_id']]
                
                report_lines.append("\nNUMA-ТОПОЛОГИЯ")
                report_lines.append("─" * 78)
                
                if not host_ids:
                    report_lines.append("    Нет данных (требуется хотя бы один хост).")
                else:
                    placeholders = ','.join(['%s'] * len(host_ids))
                    cur.execute(f"""
                        SELECT nn.vds_id::text, v.vds_name, nn.numa_node_index,
                               nn.mem_total, nn.cpu_count, 
                               ARRAY_AGG(nncm.cpu_core_id ORDER BY nncm.cpu_core_id) AS core_ids
                        FROM numa_node nn
                        JOIN vds_static v ON nn.vds_id = v.vds_id
                        LEFT JOIN numa_node_cpu_map nncm ON nn.numa_node_id = nncm.numa_node_id
                        WHERE nn.vds_id::text IN ({placeholders})
                        GROUP BY nn.vds_id, v.vds_name, nn.numa_node_index, nn.mem_total, nn.cpu_count
                        ORDER BY v.vds_name, nn.numa_node_index
                    """, tuple(host_ids))
                    
                    numa_rows = cur.fetchall()
                    
                    if not numa_rows:
                        report_lines.append("    NUMA-данные отсутствуют.")
                    else:
                        # Заголовок таблицы
                        report_lines.append(
                            f"    {'Хост':<30} │ {'Node':<6} │ {'Память':<12} │ "
                            f"{'Ядер':<6} │ {'ID ядер'}"
                        )
                        report_lines.append(
                            f"    {'─'*30}┼{'─'*8}{'─'*14}┼{'─'*8}┼{'─'*40}"
                        )
                        
                        current_host = None
                        for nr in numa_rows:
                            # Формируем читаемый диапазон/список ядер
                            cores = sorted([c for c in nr['core_ids'] if c is not None])
                            if not cores:
                                cores_str = "—"
                            elif len(cores) <= 10:
                                cores_str = ', '.join(map(str, cores))
                            else:
                                # Для больших массивов показываем начало, конец и общее число
                                cores_str = f"{cores[0]}-{cores[-1]} (всего {len(cores)})"
                            
                            # Разделитель между хостами для читаемости
                            if nr['vds_name'] != current_host:
                                current_host = nr['vds_name']
                                report_lines.append("")  # Пустая строка перед новым хостом
                            
                            report_lines.append(
                                f"    {_safe_text(nr['vds_name']):<30} │ "
                                f"{nr['numa_node_index']:<6} │ "
                                f"{_fmt_size(nr['mem_total']):<12} │ "
                                f"{nr['cpu_count'] or 0:<6} │ {cores_str}"
                            )

                # 6. CPU Profiles
                cur.execute("""
                    SELECT cp.name, cp.description
                    FROM cpu_profiles cp
                    WHERE cp.cluster_id::text = %s
                    ORDER BY cp.name
                """, (cluster_search,))
                
                profiles = cur.fetchall()
                
                report_lines.append("\nCPU PROFILES")
                report_lines.append("─" * 78)
                
                if not profiles:
                    report_lines.append("    Профили CPU не настроены.")
                else:
                    for p in profiles:
                        desc = _safe_text(p['description']) or "—"
                        report_lines.append(f"    • {_safe_text(p['name'])}: {desc}")

                # 7. Диагностика
                issues = []
                
                if not cluster['fencing_enabled']:
                    issues.append("Fencing отключен")
                if not cluster['enable_ksm']:
                    issues.append("KSM отключен (возможна неэффективная память)")
                if not cluster['enable_balloon']:
                    issues.append("Balloon отключен (нет динамического управления RAM)")
                
                non_up_hosts = sum(1 for h in hosts if h['host_status_code'] != 3)
                if non_up_hosts > 0:
                    issues.append(f"{non_up_hosts} хост(ов) не в статусе Up")

                report_lines.append(f"\nДИАГНОСТИКА ({len(issues)} замечаний)")
                report_lines.append("─" * 78)
                if issues:
                    for issue in issues:
                        report_lines.append(f"    ⚠️ {issue}")
                else:
                    report_lines.append("    Критичных проблем не обнаружено")

                report_lines.append("\n" + "═" * 78)
                
                nav_data = {
                    "cluster_id": cluster['cluster_id'],
                    "cluster_name": cluster['name'],
                    "datacenter_name": cluster['datacenter_name'],
                    "host_count": len(hosts),
                }

                return {
                    "report_text": "\n".join(report_lines),
                    "nav_data": nav_data
                }

    except Exception as e:
        return {"error": f"Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}
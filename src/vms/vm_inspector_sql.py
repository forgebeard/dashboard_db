# src/vms/vm_inspector_sql.py
"""
Модуль генерации диагностического отчета по ВМ (VM-Inspector).
Использует прямое подключение psycopg2 для сложных выборок.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (DB_USER, DB_PASSWORD и др.)
from datetime import datetime  # Работа с датой/временем для расчета Uptime и форматирования
import html             # Экранирование спецсимволов для безопасности отчета

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL для прямого подключения к БД
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.constants import VM_STATUS_MAP, IMAGE_STATUS_MAP  # Глобальные справочники статусов


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


def get_vm_inspector_report(db_name: str, vm_guid: str) -> dict:
    """
    Возвращает словарь с текстовым отчетом и навигационными данными по ВМ.
    
    Args:
        db_name: Имя базы данных (дампа)
        vm_guid: UUID виртуальной машины
        
    Returns:
        Словарь с ключами: report_text, nav_data, error (при неудаче)
    """
    vm_search = str(vm_guid).strip().lower()
    
    conn_params = {
        "dbname": db_name,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    try:
        # Контекстный менеджер гарантирует закрытие соединения даже при ошибке
        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                now_naive = datetime.now().replace(tzinfo=None)

                # 1. Основная информация (убран дублирующий JOIN на cluster)
                cur.execute("""
                    SELECT v.*, d.status as vm_status_code, d.run_on_vds, d.boot_time, 
                           c.name as cluster_name, dc.name as dc_name,
                           h.vds_name as host_name, c.storage_pool_id::text,
                           c.cluster_id::text, h.vds_id::text
                    FROM vm_static v
                    LEFT JOIN vm_dynamic d ON v.vm_guid = d.vm_guid
                    LEFT JOIN cluster c ON v.cluster_id = c.cluster_id
                    LEFT JOIN storage_pool dc ON c.storage_pool_id = dc.id
                    LEFT JOIN vds_static h ON d.run_on_vds = h.vds_id
                    WHERE v.vm_guid::text = %s LIMIT 1
                """, (vm_search,))
                
                vm = cur.fetchone()
                if not vm:
                    return {"error": "ВМ не найдена.", "report_text": "", "nav_data": {}}

                total_vcpu = (vm['num_of_sockets'] or 0) * \
                             (vm['cpu_per_socket'] or 0) * \
                             (vm['threads_per_cpu'] or 0)
                
                boot_time_naive = _safe_date(vm['boot_time'])
                uptime_text = "—"
                if vm['vm_status_code'] == 1 and boot_time_naive:
                    delta = now_naive - boot_time_naive
                    uptime_text = f"{delta.days}д {delta.seconds//3600}ч {(delta.seconds%3600)//60}м"

                current_status = VM_STATUS_MAP.get(
                    vm['vm_status_code'], 
                    f"Code {vm['vm_status_code']}"
                )

                report_lines = [
                    "═" * 78,
                    f"  VM-Inspector — Диагностический отчёт",
                    f"  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}",
                    "═" * 78,
                    "",
                    "ОСНОВНАЯ ИНФОРМАЦИЯ",
                    "─" * 78,
                    f"  Имя ВМ:        {_safe_text(vm['vm_name'])}",
                    f"  UUID:           {vm['vm_guid']}",
                    f"  Кластер:        {_safe_text(vm['cluster_name'])}",
                    f"  Дата-центр:     {_safe_text(vm['dc_name'])}",
                    f"  Хост:           {_safe_text(vm['host_name']) or '— (не запущена)'}",
                    "",
                    "   Ресурсы:",
                    f"    CPU:    {total_vcpu} vCPU",
                    f"    RAM:    {_fmt_size(vm['mem_size_mb'])}",
                    "",
                    "  Runtime:",
                    f"    Статус:     {current_status}",
                    f"    Uptime:     {uptime_text}",
                ]

                # 2. Диски (используем константы вместо магических чисел)
                locked_code = next((k for k, v in IMAGE_STATUS_MAP.items() if v == "LOCKED"), 2)
                illegal_code = next((k for k, v in IMAGE_STATUS_MAP.items() if v == "ILLEGAL"), 3)
                
                cur.execute("""
                    SELECT bd.disk_alias, bd.disk_id, i.image_guid, i.size, i.imagestatus, 
                           sd.storage_name, did.actual_size, i.active, vs.description as snap_name,
                           i.creation_date
                    FROM base_disks bd
                    JOIN vm_device vd ON bd.disk_id = vd.device_id AND vd.vm_id = %s::uuid
                    LEFT JOIN images i ON i.image_group_id = bd.disk_id
                    LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
                    LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
                    LEFT JOIN disk_image_dynamic did ON i.image_guid = did.image_id
                    LEFT JOIN snapshots vs ON i.vm_snapshot_id = vs.snapshot_id
                    ORDER BY bd.disk_alias, i.creation_date
                """, (vm['vm_guid'],))
                
                disks = cur.fetchall()
                
                report_lines.append("\nДИСКИ И СНАПШОТЫ")
                report_lines.append("─" * 78)
                
                if not disks:
                    report_lines.append("    Диски не обнаружены.")
                else:
                    current_disk = None
                    for d in disks:
                        if d['disk_alias'] != current_disk:
                            current_disk = d['disk_alias']
                            report_lines.append(f"\n   Диск: {_safe_text(current_disk)} (ID: {d['disk_id']})")
                            report_lines.append(
                                f"    {'Название снапшота':<30} │ {'Статус':<10} │ "
                                f"{'Факт.размер':<12} │ {'Создан'}"
                            )
                            report_lines.append(
                                f"    {'─'*30}┼{'─'*12}{'─'*14}┼{'─'*18}"
                            )
                        
                        virt_size = round(d['size']/1024**3, 2) if d['size'] else 0
                        actual_size = round(d['actual_size']/1024**3, 2) if d['actual_size'] else 0
                        
                        status_label = IMAGE_STATUS_MAP.get(d['imagestatus'], f"Code {d['imagestatus']}")
                        marker = " ★ ACTIVE" if d['active'] else ""
                        
                        report_lines.append(
                            f"    {_safe_text(d['snap_name']) or 'Active'}{marker:<26} │ "
                            f"{status_label:<10} │ {actual_size:>8} ГБ │ "
                            f"{_fmt_date(d['creation_date'])}"
                        )

                # 3. Сеть
                cur.execute("""
                    SELECT vni.name, vni.mac_addr, n.name as net_name
                    FROM vm_interface vni
                    LEFT JOIN vnic_profiles vp ON vni.vnic_profile_id = vp.id
                    LEFT JOIN network n ON vp.network_id = n.id
                    WHERE vni.vm_guid = %s
                """, (vm['vm_guid'],))
                nics = cur.fetchall()
                
                report_lines.append("\nСЕТЬ")
                report_lines.append("─" * 78)
                
                if not nics:
                    report_lines.append("    Сетевые интерфейсы не обнаружены.")
                else:
                    for n in nics:
                        report_lines.append(
                            f"    • {_safe_text(n['name'])} | MAC: {n['mac_addr']} | "
                            f"Net: {_safe_text(n['net_name'])}"
                        )
                    
                    cur.execute(
                        "SELECT interface_name, ipv4_addresses "
                        "FROM vm_guest_agent_interfaces WHERE vm_id = %s", 
                        (vm['vm_guid'],)
                    )
                    ips = cur.fetchall()
                    if ips:
                        report_lines.append("\n  IP-адреса (Guest Agent):")
                        for ip in ips:
                            report_lines.append(
                                f"    • {_safe_text(ip['interface_name'])}: "
                                f"{ip['ipv4_addresses'] or '—'}"
                            )
                    else:
                        report_lines.append("\n  IP-адреса (Guest Agent): Не получены.")

                # 4. Диагностика (используем константы)
                issues = []
                cur.execute("""
                    SELECT COUNT(*) FROM images i 
                    JOIN vm_device vd ON i.image_group_id = vd.device_id 
                    WHERE vd.vm_id = %s::uuid AND i.imagestatus IN (%s, %s)
                """, (vm['vm_guid'], locked_code, illegal_code))
                locked_count = cur.fetchone()['count']
                if locked_count > 0:
                    issues.insert(0, f"LOCKED образов: {locked_count}")
                
                if vm['vm_status_code'] not in [0, 1]:
                    issues.append(f"Нестандартный статус: {current_status}")

                report_lines.append(f"\nДИАГНОСТИКА ({len(issues)} проблем)")
                report_lines.append("─" * 78)
                if issues:
                    for issue in issues:
                        report_lines.append(f"    {issue}")
                else:
                    report_lines.append("    Критичных проблем не обнаружено")

                report_lines.append("\n" + "═" * 78)
                
                nav_data = {
                    "host_id": vm['vds_id'],
                    "host_name": vm['host_name'],
                    "cluster_id": vm['cluster_id'],
                    "cluster_name": vm['cluster_name']
                }

                return {
                    "report_text": "\n".join(report_lines),
                    "nav_data": nav_data
                }

    except Exception as e:
        return {"error": f"Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}
# src/hosts/host_inspector_sql.py
"""
Модуль генерации диагностического отчета по хосту (Host-Inspector).
Использует прямое подключение psycopg2 для сложных выборок.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (DB_USER, DB_PASSWORD и др.)
import sys              # Управление путями поиска модулей (sys.path)
from datetime import datetime  # Работа с датой/временем для расчета Uptime и форматирования

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL для прямого подключения к БД
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари (удобно для доступа по имени колонки)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # Добавляем корень src/ в путь поиска
from core.constants import HOST_STATUS_MAP  # Глобальный справочник статусов хостов (код -> читаемое название)

def _fmt_size(mb):
    if mb is None: return "—"
    try:
        return f"{round(float(mb)/1024, 1)} ГБ"
    except:
        return f"{mb} MB"

def _safe_date(dt):
    if not dt: return None
    return dt.replace(tzinfo=None) if hasattr(dt, 'replace') else dt

def _fmt_date(dt):
    if not dt: return "—"
    return _safe_date(dt).strftime('%d.%m.%Y %H:%M:%S')

def get_host_inspector_report(db_name: str, host_id: str) -> dict:
    """Возвращает словарь с отчетом и навигационными данными."""
    conn_params = {
        "dbname": db_name,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    conn = None
    try:
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        now_naive = datetime.now().replace(tzinfo=None)

        # 1. Основная информация
        cur.execute("""
            SELECT 
                s.vds_id, s.vds_name, s.host_name, s.cluster_id,
                d.status, d.cpu_sockets, d.cpu_cores, d.cpu_threads,
                d.physical_mem_mb, d.mem_commited, d.vm_active,
                d.software_version, d.host_os, d.kvm_version, 
                d.kernel_version, d.libvirt_version, d.pretty_name,
                d.kdump_status as kdump_code,
                c.name as cluster_name, sp.name as dc_name, sp.id as storage_pool_id
            FROM vds_static s
            JOIN vds_dynamic d ON s.vds_id = d.vds_id
            LEFT JOIN cluster c ON s.cluster_id = c.cluster_id
            LEFT JOIN storage_pool sp ON c.storage_pool_id = sp.id
            WHERE s.vds_id::text = %s LIMIT 1
        """, (host_id,))
        
        host = cur.fetchone()
        if not host: 
            cur.close(); conn.close()
            return {"error": "Хост не найден.", "report_text": "", "nav_data": {}}

        kdump_map = {0: 'Disabled', 1: 'Enabled', 2: 'Timeout'}
        total_threads = (host['cpu_sockets'] or 0) * (host['cpu_cores'] or 0) * (host['cpu_threads'] or 1)
        
        # Используем глобальную константу
        current_status = HOST_STATUS_MAP.get(host['status'], f"Code {host['status']}")
        
        report = f"""══════════════════════════════════════════════════════════════════════════════
  Host-Inspector v2.0 — Диагностический отчёт хоста
  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}
══════════════════════════════════════════════════════════════════════════════

📋 ОСНОВНАЯ ИНФОРМАЦИЯ
──────────────────────────────────────────────────────────────────────────────
  Имя хоста:     {host['vds_name']}
  ID:             {host['vds_id']}
  FQDN:           {host['host_name']}
  Кластер:        {host['cluster_name'] or '—'}
  Дата-центр:     {host['dc_name'] or '—'}
  
  🖥 Аппаратная часть:
    CPU:    {host['cpu_sockets']} сок. × {host['cpu_cores']} ядер × {host['cpu_threads'] or 1} пот. = {total_threads} потоков
    RAM:    {_fmt_size(host['physical_mem_mb'])} (физ.) / {_fmt_size(host['mem_commited'])} (занято ВМ)
    
  ⚙ ПО и статус:
    Статус:       {current_status}
    Kdump:        {kdump_map.get(host['kdump_code'], f"Code {host['kdump_code']}")}
    ОС:           {host['pretty_name'] or host['host_os'] or '—'}
    Ядро:         {host['kernel_version'] or '—'}
    VDSM:         {host['software_version'] or '—'}
    Libvirt:      {host['libvirt_version'] or '—'}
    KVM:          {host['kvm_version'] or '—'}
"""

        # 2. Сеть
        try:
            cur.execute("""
                SELECT name, mac_addr, addr, subnet, gateway, mtu, speed, is_bond, bond_name
                FROM vds_interface 
                WHERE vds_id = %s AND name != 'lo'
                ORDER BY name
            """, (host['vds_id'],))
            interfaces = cur.fetchall()
            
            if interfaces:
                report += "\n🌐 СЕТЕВЫЕ ИНТЕРФЕЙСЫ\n──────────────────────────────────────────────────────────────────────────────\n"
                for iface in interfaces:
                    bond_tag = " [BOND]" if iface['is_bond'] else ""
                    ip_info = f"IP: {iface['addr'] or '—'}" if iface['addr'] else "IP: DHCP/None"
                    report += f"  • {iface['name']}{bond_tag}\n"
                    report += f"    MAC: {iface['mac_addr']} | {ip_info} | MTU: {iface['mtu'] or '—'}\n"
                    if iface['speed']:
                        report += f"    Speed: {iface['speed']} Mbps\n"
        except Exception as e:
            report += f"\n🌐 СЕТЬ: Ошибка чтения ({e})\n"

        # 3. Хранилища
        try:
            if host['storage_pool_id']:
                cur.execute("""
                    SELECT 
                        sds.storage_name, 
                        sdd.available_disk_size, 
                        sdd.used_disk_size,
                        sds.storage_type, 
                        sds.storage_domain_type
                    FROM storage_domain_static sds
                    JOIN storage_domain_dynamic sdd ON sds.id = sdd.id
                    JOIN storage_pool_with_storage_domain spwsd ON sds.id = spwsd.storage_id
                    WHERE spwsd.storage_pool_id = %s
                    ORDER BY sds.storage_name
                """, (host['storage_pool_id'],))
                
                storages = cur.fetchall()
                if storages:
                    report += "\n💾 ХРАНИЛИЩА ДАТА-ЦЕНТРА\n──────────────────────────────────────────────────────────────────────────────\n"
                    for stg in storages:
                        avail = round(stg['available_disk_size']/1024**3, 2) if stg['available_disk_size'] else 0
                        used = round(stg['used_disk_size']/1024**3, 2) if stg['used_disk_size'] else 0
                        total = avail + used
                        usage_pct = round((used / total * 100), 1) if total > 0 else 0
                        
                        type_label = f"{stg['storage_type']} ({stg['storage_domain_type']})"
                        report += f"  • {stg['storage_name']} [{type_label}]\n"
                        report += f"    Всего: {round(total, 2)} ГБ | Занято: {used} ГБ ({usage_pct}%)\n"
        except Exception as e:
            report += f"\n💾 ХРАНИЛИЩА: Ошибка чтения ({e})\n"

        # 4. ВМ на хосте
        try:
            cur.execute("""
                SELECT vs.vm_name, vd.status, vd.client_ip
                FROM vm_static vs
                JOIN vm_dynamic vd ON vs.vm_guid = vd.vm_guid
                WHERE vd.run_on_vds = %s
                ORDER BY vs.vm_name
            """, (host['vds_id'],))
            vms = cur.fetchall()
            
            report += f"\n🖥 ВИРТУАЛЬНЫЕ МАШИНЫ ({len(vms)})\n──────────────────────────────────────────────────────────────────────────────\n"
            if vms:
                for vm in vms:
                    status_icon = "▶️" if vm['status'] == 1 else "⏹️"
                    report += f"  {status_icon} {vm['vm_name']} (статус: {vm['status']})\n"
                    if vm['client_ip']:
                        report += f"      IP: {vm['client_ip']}\n"
            else:
                report += "  ✅ Нет запущенных ВМ\n"
        except Exception as e:
            report += f"\n🖥 ВМ: Ошибка чтения ({e})\n"

        # 5. Аудит
        try:
            cur.execute("""
                SELECT log_time, log_type_name, user_name, message 
                FROM audit_log 
                WHERE vds_id = %s OR vds_name = %s 
                ORDER BY log_time DESC LIMIT 5
            """, (host['vds_id'], host['vds_name']))
            logs = cur.fetchall()
            
            if logs:
                report += "\n📜 АУДИТ (последние 5 событий)\n──────────────────────────────────────────────────────────────────────────────\n"
                for l in logs:
                    msg = l['message'][:150] + "..." if len(l['message']) > 150 else l['message']
                    report += f"  ℹ️ [{_fmt_date(l['log_time'])}] {l['log_type_name']} (user: {l['user_name'] or '—'})\n    {msg}\n"
        except Exception as e:
            report += f"\n📜 АУДИТ: Ошибка чтения ({e})\n"

        # 6. Диагностика
        issues = []
        if host['status'] == 4: issues.append("🔴 Статус NonResponsive — хост не отвечает!")
        if host['status'] == 5: issues.append("🔴 Статус Error")
        if host['status'] == 10: issues.append("⚠️ Статус NonOperational")
        if host['kdump_code'] != 1: issues.append("⚠️ Kdump отключен или в ошибке")

        report += f"\n🔍 ДИАГНОСТИКА ({len(issues)} проблем)\n──────────────────────────────────────────────────────────────────────────────\n"
        if issues:
            for issue in issues: report += f"  {issue}\n"
        else:
            report += "  ✅ Критичных проблем не обнаружено\n"

        report += "\n══════════════════════════════════════════════════════════════════════════════\n"
        
        cur.close()
        conn.close()

        nav_data = {
            "cluster_id": host['cluster_id'],
            "cluster_name": host['cluster_name'],
            "dc_name": host['dc_name']
        }

        return {
            "report_text": report,
            "nav_data": nav_data
        }

    except Exception as e:
        import traceback
        return {"error": f"❌ Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}
    finally:
        if conn and not conn.closed:
            conn.close()
# src/networks/network_inspector_sql.py
"""
Модуль генерации диагностического отчета по сети (Network-Inspector).
Использует прямое подключение psycopg2 для сложных выборок и анализа связей 
с кластерами, профилями vNIC и физическими интерфейсами хостов.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (DB_USER, DB_PASSWORD и др.)
from datetime import datetime  # Работа с датой/временем для форматирования отчетов

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL для прямого подключения к БД
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари (удобно для доступа по имени колонки)

def _fmt_date(dt):
    if not dt: return "—"
    naive_dt = dt.replace(tzinfo=None) if hasattr(dt, 'replace') else dt
    return naive_dt.strftime('%d.%m.%Y %H:%M:%S')

def get_network_inspector_report(db_name: str, network_id: str) -> str:
    conn_params = {
        "dbname": db_name,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    try:
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # 1. Основная информация о сети
        cur.execute("""
            SELECT n.id::text, n.name, n.description, n.vlan_id, n.vm_network, 
                   sp.name as dc_name, drc.id::text as dns_config_id, n.mtu, n.stp, 
                   n.label, n.vdsm_name, n.subnet, n.gateway, n.free_text_comment
            FROM network n
            LEFT JOIN storage_pool sp ON n.storage_pool_id = sp.id
            LEFT JOIN dns_resolver_configuration drc ON n.dns_resolver_configuration_id = drc.id
            WHERE n.id = %s LIMIT 1
        """, (network_id,))
        
        net = cur.fetchone()
        if not net: return "❌ Сеть не найдена."

        report = f"""══════════════════════════════════════════════════════════════════════════════
  Network-Inspector v1.0 — Диагностический отчёт
  Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
══════════════════════════════════════════════════════════════════════════════

📋 ОСНОВНАЯ ИНФОРМАЦИЯ
──────────────────────────────────────────────────────────────────────────────
  Имя сети:     {net['name']}
  UUID:         {net['id']}
  Описание:     {net['description'] or '—'}
  Дата-центр:   {net['dc_name'] or '—'}
  VDSM Name:    {net['vdsm_name'] or '—'}
  VM Network:   {'✅ Да' if net['vm_network'] else '❌ Нет'}
  VLAN ID:      {net['vlan_id'] if net['vlan_id'] is not None else '—'}
  MTU:          {net['mtu']}
  STP:          {'✅ Вкл' if net['stp'] else '❌ Выкл'}
  Label:        {net['label'] or '—'}

  🌐 Настройки IP (если есть):
    Subnet:     {net['subnet'] or '—'}
    Gateway:    {net['gateway'] or '—'}
    Free Text:  {net['free_text_comment'] or '—'}
"""

        # 2. Привязка к кластерам
        cur.execute("""
            SELECT nc.status, c.name as cluster_name, nc.is_display, nc.required, 
                   nc.management, nc.default_route
            FROM network_cluster nc
            JOIN cluster c ON nc.cluster_id = c.cluster_id
            WHERE nc.network_id = %s
        """, (network_id,))
        clusters = cur.fetchall()
        
        report += "\n🏢 ПРИВЯЗКА К КЛАСТЕРАМ\n──────────────────────────────────────────────────────────────────────────────\n"
        if clusters:
            for cl in clusters:
                report += f"  • Кластер: {cl['cluster_name']}\n"
                report += f"    Статус: {cl['status']} | Отображать: {'✅' if cl['is_display'] else '❌'} | Req: {'✅' if cl['required'] else '❌'}\n"
                report += f"    Management: {'✅' if cl['management'] else '❌'} | Default Route: {'✅' if cl['default_route'] else '❌'}\n\n"
        else:
            report += "  ℹ️ Не привязана ни к одному кластеру.\n"

        # 3. Профили vNIC
        cur.execute("""
            SELECT vp.name, vp.port_mirroring, vp.passthrough, vp.migratable, 
                   nf.filter_name, qos.name as qos_name
            FROM vnic_profiles vp
            LEFT JOIN network_filter nf ON vp.network_filter_id = nf.filter_id
            LEFT JOIN qos ON vp.network_qos_id = qos.id
            WHERE vp.network_id = %s
        """, (network_id,))
        profiles = cur.fetchall()
        
        report += "\n🔌 ПРОФИЛИ vNIC\n──────────────────────────────────────────────────────────────────────────────\n"
        if profiles:
            for p in profiles:
                report += f"  • Профиль: {p['name']}\n"
                report += f"    Port Mirroring: {'✅' if p['port_mirroring'] else '❌'} | Passthrough: {'✅' if p['passthrough'] else '❌'}\n"
                report += f"    Migratable: {'✅' if p['migratable'] else '❌'}\n"
                report += f"    Filter: {p['filter_name'] or '—'} | QoS: {p['qos_name'] or '—'}\n\n"
        else:
            report += "  ℹ️ Профили не настроены.\n"

        # 4. DNS Конфигурация
        if net['dns_config_id']:
            cur.execute("""
                SELECT ns.address, ns.position
                FROM name_server ns
                WHERE ns.dns_resolver_configuration_id = %s
                ORDER BY ns.position
            """, (net['dns_config_id'],))
            servers = cur.fetchall()
            
            report += "\n📡 DNS СЕРВЕРЫ\n──────────────────────────────────────────────────────────────────────────────\n"
            if servers:
                for s in servers:
                    report += f"  • {s['address']} (Priority: {s['position']})\n"
            else:
                report += "  ℹ️ Серверы не настроены.\n"
        else:
             report += "\n📡 DNS СЕРВЕРЫ\n──────────────────────────────────────────────────────────────────────────────\n"
             report += "  ℹ️ Для этой сети конфигурация DNS не задана.\n"

        # 5. Подключения на хостах (через vds_interface)
        # Используем поиск по имени сети, так как это основной способ связки в oVirt
        cur.execute("""
            SELECT vi.name as iface_name, vi.vds_id, v.vds_name, vi.vlan_id, vi.speed, vi.bridged
            FROM vds_interface vi
            JOIN vds_static v ON vi.vds_id = v.vds_id
            WHERE vi.network_name = %s OR (vi.vlan_id = %s AND vi.network_name IS NOT NULL)
            LIMIT 50
        """, (net['name'], net['vlan_id']))
        hosts_ifaces = cur.fetchall()

        report += "\n🖥 ПОДКЛЮЧЕНИЯ НА ХОСТАХ (Превью)\n──────────────────────────────────────────────────────────────────────────────\n"
        if hosts_ifaces:
            report += f"  Найдено подключений: {len(hosts_ifaces)} (показаны первые 50)\n"
            for h in hosts_ifaces:
                report += f"  • Хост: {h['vds_name']} | Интерфейс: {h['iface_name']} | VLAN: {h['vlan_id']} | Speed: {h['speed']} Mbps\n"
        else:
            report += "  ℹ️ Активных подключений на хостах не найдено по имени/VLAN.\n"

        report += "\n══════════════════════════════════════════════════════════════════════════════\n"
        
        cur.close()
        conn.close()
        return report

    except Exception as e:
        import traceback
        return f"❌ Ошибка инспектора сетей: {e}\n{traceback.format_exc()}"
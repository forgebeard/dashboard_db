# src/networks/network_inspector_sql.py
"""
Модуль генерации диагностического отчета по сети (Network-Inspector).
Использует InspectorBase для подключения через SQLAlchemy.
"""

from datetime import datetime
import traceback

from core.inspector_base import InspectorBase


def _fmt_date(dt):
    if not dt:
        return "—"
    naive_dt = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
    return naive_dt.strftime("%d.%m.%Y %H:%M:%S")


def get_network_inspector_report(db_name: str, network_id: str) -> str:
    try:
        with InspectorBase(db_name) as insp:
            net = insp.fetch_one(
                """
                SELECT n.id::text, n.name, n.description, n.vlan_id, n.vm_network,
                       sp.name as dc_name, drc.id::text as dns_config_id, n.mtu, n.stp,
                       n.label, n.vdsm_name, n.subnet, n.gateway, n.free_text_comment
                FROM network n
                LEFT JOIN storage_pool sp ON n.storage_pool_id = sp.id
                LEFT JOIN dns_resolver_configuration drc ON n.dns_resolver_configuration_id = drc.id
                WHERE n.id = :network_id LIMIT 1
                """,
                {"network_id": network_id},
            )

            if not net:
                return "❌ Сеть не найдена."

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

            clusters = insp.fetch_all(
                """
                SELECT nc.status, c.name as cluster_name, nc.is_display, nc.required,
                       nc.management, nc.default_route
                FROM network_cluster nc
                JOIN cluster c ON nc.cluster_id = c.cluster_id
                WHERE nc.network_id = :network_id
                """,
                {"network_id": network_id},
            )

            report += "\n🏢 ПРИВЯЗКА К КЛАСТЕРАМ\n──────────────────────────────────────────────────────────────────────────────\n"
            if clusters:
                for cl in clusters:
                    report += f"  • Кластер: {cl['cluster_name']}\n"
                    report += (
                        f"    Статус: {cl['status']} | Отображать: "
                        f"{'✅' if cl['is_display'] else '❌'} | Req: {'✅' if cl['required'] else '❌'}\n"
                    )
                    report += (
                        f"    Management: {'✅' if cl['management'] else '❌'} | "
                        f"Default Route: {'✅' if cl['default_route'] else '❌'}\n\n"
                    )
            else:
                report += "  ℹ️ Не привязана ни к одному кластеру.\n"

            profiles = insp.fetch_all(
                """
                SELECT vp.name, vp.port_mirroring, vp.passthrough, vp.migratable,
                       nf.filter_name, qos.name as qos_name
                FROM vnic_profiles vp
                LEFT JOIN network_filter nf ON vp.network_filter_id = nf.filter_id
                LEFT JOIN qos ON vp.network_qos_id = qos.id
                WHERE vp.network_id = :network_id
                """,
                {"network_id": network_id},
            )

            report += "\n🔌 ПРОФИЛИ vNIC\n──────────────────────────────────────────────────────────────────────────────\n"
            if profiles:
                for p in profiles:
                    report += f"  • Профиль: {p['name']}\n"
                    report += (
                        f"    Port Mirroring: {'✅' if p['port_mirroring'] else '❌'} | "
                        f"Passthrough: {'✅' if p['passthrough'] else '❌'}\n"
                    )
                    report += f"    Migratable: {'✅' if p['migratable'] else '❌'}\n"
                    report += f"    Filter: {p['filter_name'] or '—'} | QoS: {p['qos_name'] or '—'}\n\n"
            else:
                report += "  ℹ️ Профили не настроены.\n"

            if net["dns_config_id"]:
                servers = insp.fetch_all(
                    """
                    SELECT ns.address, ns.position
                    FROM name_server ns
                    WHERE ns.dns_resolver_configuration_id = :dns_config_id
                    ORDER BY ns.position
                    """,
                    {"dns_config_id": net["dns_config_id"]},
                )

                report += "\n📡 DNS СЕРВЕРЫ\n──────────────────────────────────────────────────────────────────────────────\n"
                if servers:
                    for s in servers:
                        report += f"  • {s['address']} (Priority: {s['position']})\n"
                else:
                    report += "  ℹ️ Серверы не настроены.\n"
            else:
                report += "\n📡 DNS СЕРВЕРЫ\n──────────────────────────────────────────────────────────────────────────────\n"
                report += "  ℹ️ Для этой сети конфигурация DNS не задана.\n"

            hosts_ifaces = insp.fetch_all(
                """
                SELECT vi.name as iface_name, vi.vds_id, v.vds_name, vi.vlan_id, vi.speed, vi.bridged
                FROM vds_interface vi
                JOIN vds_static v ON vi.vds_id = v.vds_id
                WHERE vi.network_name = :net_name
                   OR (vi.vlan_id = :vlan_id AND vi.network_name IS NOT NULL)
                LIMIT 50
                """,
                {"net_name": net["name"], "vlan_id": net["vlan_id"]},
            )

            report += "\n🖥 ПОДКЛЮЧЕНИЯ НА ХОСТАХ (Превью)\n──────────────────────────────────────────────────────────────────────────────\n"
            if hosts_ifaces:
                report += f"  Найдено подключений: {len(hosts_ifaces)} (показаны первые 50)\n"
                for h in hosts_ifaces:
                    report += (
                        f"  • Хост: {h['vds_name']} | Интерфейс: {h['iface_name']} | "
                        f"VLAN: {h['vlan_id']} | Speed: {h['speed']} Mbps\n"
                    )
            else:
                report += "  ℹ️ Активных подключений на хостах не найдено по имени/VLAN.\n"

            report += "\n══════════════════════════════════════════════════════════════════════════════\n"
            return report

    except Exception as e:
        return f"❌ Ошибка инспектора сетей: {e}\n{traceback.format_exc()}"

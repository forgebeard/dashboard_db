"""Диагностический отчёт по логической сети. Сбор отдельно от вёрстки."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.constants import mapped_code_label
from core.inspector_base import InspectorBase
from vms.vm_inspector_sql import BAR_DOUBLE, BAR_SINGLE, _kv, _kv_at, _yes_no

HOST_ATTACHMENTS_SQL = """
SELECT
    v.vds_name,
    v.vds_id::text AS vds_id,
    vi.name AS iface_name,
    vi.vlan_id,
    na.address
FROM network_attachments na
JOIN vds_interface vi ON na.nic_id = vi.id
JOIN vds_static v ON vi.vds_id = v.vds_id
WHERE na.network_id::text = :network_id
ORDER BY v.vds_name, vi.name
"""


def _raw_code_label(code: Any) -> str:
    if code in (None, ""):
        return "—"
    return mapped_code_label(code, {})


def format_network_report(payload: dict[str, Any]) -> str:
    """Текстовый отчёт: сеть, кластеры, профили, DNS, хосты, ВМ."""
    header = payload.get("header") or {}
    clusters = payload.get("clusters") or []
    profiles = payload.get("profiles") or []
    dns = payload.get("dns") or []
    hosts = payload.get("hosts") or []
    vms = payload.get("vms") or []
    section_errors = payload.get("section_errors") or {}
    generated_at = payload.get("generated_at") or "—"

    vlan = header.get("vlan_id")
    vlan_text = "—" if vlan is None or vlan == "" else str(vlan)

    lines = [
        BAR_DOUBLE,
        f"  Network-Inspector                                      {generated_at}",
        BAR_DOUBLE,
        "",
        "СЕТЬ",
        BAR_SINGLE,
    ]
    if not header:
        lines.append("  сеть не найдена")
    else:
        lines.append(_kv("имя", header.get("name") or "—"))
        lines.append(_kv("UUID", header.get("id")))
        lines.append(_kv("дата-центр", header.get("dc_name") or "—"))
        lines.append(_kv("описание", header.get("description") or "—"))
        lines.append(_kv("VLAN", vlan_text))
        lines.append(_kv("MTU", header.get("mtu")))
        lines.append(_kv("vm_network", _yes_no(header.get("vm_network"))))
        lines.append(_kv("vdsm_name", header.get("vdsm_name") or "—"))
        lines.append(_kv("type", _raw_code_label(header.get("type"))))
        lines.append(_kv("STP", _yes_no(header.get("stp"))))
        lines.append(_kv("label", header.get("label") or "—"))
        lines.append(_kv("subnet", header.get("subnet") or "—"))
        lines.append(_kv("gateway", header.get("gateway") or "—"))

    lines += ["", "КЛАСТЕРЫ", BAR_SINGLE]
    if section_errors.get("clusters"):
        lines.append(f"  ошибка чтения ({section_errors['clusters']})")
    elif not clusters:
        lines.append("  нет кластеров")
    else:
        for row in clusters:
            lines.append(_kv_at("    ", "кластер", row.get("cluster_name") or "—"))
            lines.append(_kv_at("    ", "UUID", row.get("cluster_id")))
            lines.append(_kv_at("    ", "статус", _raw_code_label(row.get("status"))))
            lines.append(_kv_at("    ", "management", _yes_no(row.get("management"))))
            lines.append(_kv_at("    ", "required", _yes_no(row.get("required"))))
            lines.append(_kv_at("    ", "display", _yes_no(row.get("is_display"))))
            lines.append(_kv_at("    ", "migration", _yes_no(row.get("migration"))))
            lines.append(_kv_at("    ", "gluster", _yes_no(row.get("is_gluster"))))
            lines.append(_kv_at("    ", "default_route", _yes_no(row.get("default_route"))))
            lines.append("")

    lines += ["", "ПРОФИЛИ", BAR_SINGLE]
    if section_errors.get("profiles"):
        lines.append(f"  ошибка чтения ({section_errors['profiles']})")
    elif not profiles:
        lines.append("  нет профилей")
    else:
        for row in profiles:
            lines.append(_kv_at("    ", "профиль", row.get("name") or "—"))
            lines.append(_kv_at("    ", "UUID", row.get("id")))
            lines.append(_kv_at("    ", "mirroring", _yes_no(row.get("port_mirroring"))))
            lines.append(_kv_at("    ", "passthrough", _yes_no(row.get("passthrough"))))
            lines.append(_kv_at("    ", "migratable", _yes_no(row.get("migratable"))))
            lines.append(_kv_at("    ", "filter", row.get("filter_name") or "—"))
            lines.append(_kv_at("    ", "QoS", row.get("qos_name") or "—"))
            lines.append("")

    lines += ["", "DNS", BAR_SINGLE]
    if section_errors.get("dns"):
        lines.append(f"  ошибка чтения ({section_errors['dns']})")
    elif not dns:
        lines.append("  нет DNS")
    else:
        for row in dns:
            addr = row.get("address") or "—"
            pos = row.get("position")
            extra = f"    {pos}" if pos not in (None, "") else ""
            lines.append(_kv_at("    ", "сервер", f"{addr}{extra}"))

    lines += ["", "ХОСТЫ", BAR_SINGLE]
    if section_errors.get("hosts"):
        lines.append(f"  ошибка чтения ({section_errors['hosts']})")
    elif not hosts:
        lines.append("  нет хостов")
    else:
        for row in hosts:
            lines.append(_kv_at("    ", "хост", row.get("vds_name") or "—"))
            lines.append(_kv_at("    ", "UUID", row.get("vds_id")))
            lines.append(_kv_at("    ", "NIC", row.get("iface_name") or "—"))
            vlan_if = row.get("vlan_id")
            lines.append(
                _kv_at("    ", "VLAN", "—" if vlan_if in (None, "") else vlan_if)
            )
            lines.append(_kv_at("    ", "address", row.get("address") or "—"))
            lines.append("")

    lines += ["", "ВМ", BAR_SINGLE]
    if section_errors.get("vms"):
        lines.append(f"  ошибка чтения ({section_errors['vms']})")
    elif not vms:
        lines.append("  нет ВМ")
    else:
        for row in vms:
            lines.append(_kv_at("    ", "ВМ", row.get("vm_name") or "—"))
            lines.append(_kv_at("    ", "UUID", row.get("vm_id")))
            lines.append(_kv_at("    ", "MAC", row.get("mac_addr") or "—"))
            lines.append(_kv_at("    ", "профиль", row.get("profile_name") or "—"))
            lines.append("")

    lines.append(BAR_DOUBLE)
    return "\n".join(lines)


def get_network_inspector_report(db_name: str, network_id: str) -> dict:
    """Отчёт по логической сети."""
    net_search = str(network_id).strip()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)
            net = insp.fetch_one(
                """
                SELECT
                    n.id::text,
                    n.name,
                    n.description,
                    n.vlan_id,
                    n.vm_network,
                    n.mtu,
                    n.stp,
                    n.label,
                    n.vdsm_name,
                    n.subnet,
                    n.gateway,
                    n.type,
                    n.dns_resolver_configuration_id::text AS dns_config_id,
                    sp.name AS dc_name
                FROM network n
                LEFT JOIN storage_pool sp ON n.storage_pool_id = sp.id
                WHERE n.id::text = :network_id
                LIMIT 1
                """,
                {"network_id": net_search},
            )
            if not net:
                return {"error": "Сеть не найдена.", "report_text": "", "nav_data": {}}

            section_errors: dict[str, str] = {}
            params = {"network_id": net["id"]}

            clusters: list[dict[str, Any]] = []
            try:
                clusters = insp.fetch_all(
                    """
                    SELECT
                        c.name AS cluster_name,
                        c.cluster_id::text AS cluster_id,
                        nc.status,
                        nc.is_display,
                        nc.required,
                        nc.management,
                        nc.default_route,
                        nc.migration,
                        nc.is_gluster
                    FROM network_cluster nc
                    JOIN cluster c ON nc.cluster_id = c.cluster_id
                    WHERE nc.network_id::text = :network_id
                    ORDER BY c.name
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["clusters"] = str(exc)

            profiles: list[dict[str, Any]] = []
            try:
                profiles = insp.fetch_all(
                    """
                    SELECT
                        vp.id::text,
                        vp.name,
                        vp.port_mirroring,
                        vp.passthrough,
                        vp.migratable,
                        nf.filter_name,
                        qos.name AS qos_name
                    FROM vnic_profiles vp
                    LEFT JOIN network_filter nf ON vp.network_filter_id = nf.filter_id
                    LEFT JOIN qos ON vp.network_qos_id = qos.id
                    WHERE vp.network_id::text = :network_id
                    ORDER BY vp.name
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["profiles"] = str(exc)

            dns: list[dict[str, Any]] = []
            dns_id = net.get("dns_config_id")
            if dns_id:
                try:
                    dns = insp.fetch_all(
                        """
                        SELECT ns.address, ns.position
                        FROM name_server ns
                        WHERE ns.dns_resolver_configuration_id::text = :dns_config_id
                        ORDER BY ns.position
                        """,
                        {"dns_config_id": dns_id},
                    )
                except Exception as exc:
                    section_errors["dns"] = str(exc)

            hosts: list[dict[str, Any]] = []
            try:
                hosts = insp.fetch_all(HOST_ATTACHMENTS_SQL, params)
            except Exception as exc:
                section_errors["hosts"] = str(exc)

            vms: list[dict[str, Any]] = []
            try:
                vms = insp.fetch_all(
                    """
                    SELECT
                        vm.vm_name,
                        vm.vm_guid::text AS vm_id,
                        vni.mac_addr,
                        vp.name AS profile_name
                    FROM vm_interface vni
                    JOIN vnic_profiles vp ON vni.vnic_profile_id = vp.id
                    JOIN vm_static vm ON vni.vm_guid = vm.vm_guid
                    WHERE vp.network_id::text = :network_id
                    ORDER BY vm.vm_name, vni.name
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["vms"] = str(exc)

            payload = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "header": net,
                "clusters": clusters,
                "profiles": profiles,
                "dns": dns,
                "hosts": hosts,
                "vms": vms,
                "section_errors": section_errors,
                "nav_data": {
                    "network_id": net["id"],
                    "network_name": net["name"],
                },
            }
            payload["report_text"] = format_network_report(payload)
            return payload

    except Exception as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

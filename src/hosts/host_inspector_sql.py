# src/hosts/host_inspector_sql.py
"""
Модуль генерации диагностического отчета по хосту (Host-Inspector).
Использует InspectorBase для безопасного подключения через SQLAlchemy.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from core.constants import HOST_STATUS_MAP
from core.exceptions import DataLoadError, should_retry_narrow_sql
from core.inspector_base import InspectorBase
from core.report_text import BAR_DOUBLE, BAR_SINGLE, _fmt_date, _kv, _yes_no

KDUMP_MAP = {0: "Disabled", 1: "Enabled", 2: "Timeout"}

AUDIT_TYPE_LABELS = {
    "VM_CONSOLE_DISCONNECTED": "console disconnected",
    "VM_CONSOLE_CONNECTED": "console connected",
    "VM_SET_TICKET": "console ticket",
    "USER_RESET_VM": "VM reset",
    "USER_ATTACH_DISK_TO_VM": "disk attached",
}

_ATTACH_DISK_RE = re.compile(
    r"Disk (\S+) was successfully attached to VM (\S+)", re.IGNORECASE
)
_VM_NAME_RE = re.compile(r"\bVM (\S+)")


def _fmt_size_mb(mb: Any) -> str:
    """Форматирует размер из МБ в ГБ."""
    if mb is None:
        return "—"
    try:
        return f"{round(float(mb) / 1024, 1)} ГБ"
    except (ValueError, TypeError):
        return f"{mb} MB"


def _fmt_speed(mbps: Any) -> str:
    if mbps in (None, ""):
        return ""
    try:
        n = int(float(mbps))
    except (TypeError, ValueError):
        return str(mbps)
    if n >= 1000 and n % 1000 == 0:
        return f"{n // 1000}G"
    return f"{n} Mbps"


def _fmt_mac(mac: Any) -> str:
    if mac in (None, "", "None"):
        return ""
    return str(mac)


def _is_bond(iface: dict[str, Any]) -> bool:
    flag = iface.get("is_bond")
    return flag in (True, 1, "1", "t", "true", "True")


def _vlan_id(iface: dict[str, Any]) -> int | None:
    vid = iface.get("vlan_id")
    if vid not in (None, ""):
        try:
            return int(vid)
        except (TypeError, ValueError):
            pass
    name = str(iface.get("name") or "")
    if "." in name:
        tail = name.rsplit(".", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return None


def _vlan_parent(iface: dict[str, Any]) -> str:
    bond = iface.get("bond_name")
    if bond:
        return str(bond)
    name = str(iface.get("name") or "")
    if "." in name:
        return name.rsplit(".", 1)[0]
    return ""


def group_host_interfaces(interfaces: list[dict[str, Any]]) -> dict[str, Any]:
    """Раскладывает NIC на L3, агрегаты, VLAN и остальные."""
    ifaces = [row for row in interfaces if (row.get("name") or "") != "lo"]
    bonds = [row for row in ifaces if _is_bond(row)]
    with_ip = [row for row in ifaces if row.get("addr")]

    slaves_by_bond: dict[str, list[dict[str, Any]]] = {}
    for row in ifaces:
        bond_name = row.get("bond_name")
        if bond_name and not _is_bond(row) and _vlan_id(row) is None:
            slaves_by_bond.setdefault(str(bond_name), []).append(row)

    vlans_by_parent: dict[str, list[int]] = {}
    vlan_names: set[str] = set()
    for row in ifaces:
        vid = _vlan_id(row)
        if vid is None:
            continue
        vlan_names.add(str(row.get("name")))
        parent = _vlan_parent(row)
        vlans_by_parent.setdefault(parent, []).append(vid)
    vlans_by_parent = {key: sorted(set(vals)) for key, vals in vlans_by_parent.items()}

    used_names = {str(row.get("name")) for row in with_ip}
    used_names.update(str(row.get("name")) for row in bonds)
    for slaves in slaves_by_bond.values():
        used_names.update(str(row.get("name")) for row in slaves)
    used_names.update(vlan_names)

    others = [row for row in ifaces if str(row.get("name")) not in used_names]
    return {
        "with_ip": with_ip,
        "bonds": bonds,
        "slaves_by_bond": slaves_by_bond,
        "vlans_by_parent": vlans_by_parent,
        "others": others,
    }


def audit_type_label(log_type_name: str | None) -> str:
    name = log_type_name or "—"
    return AUDIT_TYPE_LABELS.get(name, name)


def audit_object(log_type_name: str | None, message: str | None) -> str:
    msg = message or ""
    if log_type_name == "USER_ATTACH_DISK_TO_VM":
        match = _ATTACH_DISK_RE.search(msg)
        if match:
            return f"{match.group(1)} -> {match.group(2)}"
    match = _VM_NAME_RE.search(msg)
    if match:
        return match.group(1).rstrip(".,")
    return ""


def compact_audit_line(event: dict[str, Any]) -> str:
    when = _fmt_date(event.get("log_time"))
    label = audit_type_label(event.get("log_type_name"))
    obj = audit_object(event.get("log_type_name"), event.get("message"))
    user = event.get("user_name") or "—"
    parts = [f"  {when:<18}{label:<24}"]
    if obj:
        parts.append(f"{obj:<28}")
    parts.append(str(user))
    return "".join(parts).rstrip()


def _cpu_label(sockets: Any, cores: Any, threads: Any) -> str:
    sock = sockets if sockets is not None else "—"
    core = cores if cores is not None else "—"
    line = f"{sock} сокета × {core} ядер"
    if threads not in (None, "", 0, "0"):
        line += f"    потоки: {threads}"
    return line


def _ram_label(phys_mb: Any, committed_mb: Any) -> str:
    phys = _fmt_size_mb(phys_mb)
    committed = _fmt_size_mb(committed_mb)
    line = f"{phys} физ.  /  {committed} под ВМ"
    try:
        p = float(phys_mb)
        c = float(committed_mb)
        if p > 0:
            line += f"  ({round(c / p * 100)}%)"
    except (TypeError, ValueError):
        pass
    return line


def format_host_report(payload: dict[str, Any]) -> str:
    """Собирает текстовый отчёт по согласованному макету."""
    header = payload.get("header") or {}
    metrics = payload.get("metrics") or {}
    versions = payload.get("versions") or {}
    grouped = group_host_interfaces(payload.get("networks") or [])
    events = payload.get("events") or []
    section_errors = payload.get("section_errors") or {}
    generated_at = payload.get("generated_at") or "—"

    lines = [
        BAR_DOUBLE,
        f"  Host-Inspector                                     {generated_at}",
        BAR_DOUBLE,
        "",
        "СВЕДЕНИЯ О ХОСТЕ",
        BAR_SINGLE,
        _kv("Имя хоста", header.get("name")),
        _kv("ID", header.get("id")),
        _kv("FQDN", header.get("fqdn")),
        _kv("Кластер", header.get("cluster")),
        _kv("Дата-центр", header.get("dc")),
        _kv("Создан", header.get("created")),
        _kv("Обновлён", header.get("updated")),
        "",
        "РЕСУРСЫ",
        BAR_SINGLE,
        _kv("Статус", metrics.get("status")),
        _kv("Kdump", metrics.get("kdump")),
        _kv("SPM", metrics.get("spm")),
        _kv("CPU", metrics.get("cpu")),
        _kv("Модель CPU", metrics.get("cpu_model")),
        _kv("RAM", metrics.get("ram")),
        _kv("ВМ на хосте", metrics.get("vm_active")),
        "",
        "ВЕРСИИ",
        BAR_SINGLE,
        _kv("ОС", versions.get("os")),
        _kv("Ядро", versions.get("kernel")),
        _kv("VDSM", versions.get("vdsm")),
        _kv("Libvirt", versions.get("libvirt")),
        _kv("KVM", versions.get("kvm")),
        "",
    ]

    engine8 = payload.get("engine8") or {}
    engine8_err = section_errors.get("engine8")
    if engine8_err or engine8:
        lines += [
            "РЕД ВИРТ 8",
            BAR_SINGLE,
        ]
        if engine8_err:
            lines.append(f"  ошибка чтения ({engine8_err})")
        else:
            if "cpu_topology" in engine8:
                lines.append(_kv("CPU topology", engine8["cpu_topology"]))
            if "ovn_configured" in engine8:
                lines.append(_kv("OVN", engine8["ovn_configured"]))
            if "vdsm_cpus_affinity" in engine8:
                lines.append(_kv("VDSM affinity", engine8["vdsm_cpus_affinity"]))
        lines.append("")

    lines += [
        "СЕТЕВЫЕ ИНТЕРФЕЙСЫ",
        BAR_SINGLE,
    ]

    if section_errors.get("networks"):
        lines.append(f"  ошибка чтения ({section_errors['networks']})")
    else:
        nets = payload.get("networks") or []
        if not nets:
            lines.append("  нет интерфейсов")
        else:
            if grouped["with_ip"]:
                lines.append("  С адресом:")
                for iface in grouped["with_ip"]:
                    extra = []
                    speed = _fmt_speed(iface.get("speed"))
                    if speed:
                        extra.append(speed)
                    if iface.get("mtu") not in (None, ""):
                        extra.append(f"MTU {iface['mtu']}")
                    mac = _fmt_mac(iface.get("mac_addr"))
                    if mac:
                        extra.append(f"MAC {mac}")
                    tail = ("    " + "    ".join(extra)) if extra else ""
                    lines.append(
                        f"    {iface.get('name') or '—'!s:<14}{iface.get('addr') or '—'}{tail}"
                    )
                lines.append("")
            for bond in grouped["bonds"]:
                speed = _fmt_speed(bond.get("speed"))
                mac = _fmt_mac(bond.get("mac_addr"))
                ip_bit = bond.get("addr") or "IPv4 нет"
                bits = [f"  Агрегат {bond.get('name') or '—'}"]
                if speed:
                    bits.append(speed)
                if bond.get("mtu") not in (None, ""):
                    bits.append(f"MTU {bond['mtu']}")
                if mac:
                    bits.append(f"MAC {mac}")
                bits.append(ip_bit if bond.get("addr") else "IPv4 нет")
                lines.append("    ".join(bits))
                ports = grouped["slaves_by_bond"].get(str(bond.get("name")), [])
                if ports:
                    port_bits = []
                    for port in ports:
                        label = str(port.get("name") or "—")
                        ps = _fmt_speed(port.get("speed"))
                        port_bits.append(f"{label} ({ps})" if ps else label)
                    lines.append(f"    порты:        {', '.join(port_bits)}")
                vids = grouped["vlans_by_parent"].get(str(bond.get("name")), [])
                if vids:
                    lines.append(f"    VLAN:         {' '.join(str(v) for v in vids)}")
                lines.append("")
            leftover_vlans = {
                parent: vids
                for parent, vids in grouped["vlans_by_parent"].items()
                if parent not in {str(b.get("name")) for b in grouped["bonds"]}
            }
            for parent, vids in leftover_vlans.items():
                if not vids:
                    continue
                lines.append(f"  VLAN {parent or '—'}: {' '.join(str(v) for v in vids)}")
            if grouped["others"]:
                lines.append("  Остальные:")
                for iface in grouped["others"]:
                    speed = _fmt_speed(iface.get("speed"))
                    mac = _fmt_mac(iface.get("mac_addr"))
                    extra = []
                    if speed:
                        extra.append(speed)
                    if mac:
                        extra.append(f"MAC {mac}")
                    tail = ("    " + "    ".join(extra)) if extra else ""
                    lines.append(f"    {iface.get('name') or '—'!s:<14}{tail}".rstrip())

    lines += ["", "ЖУРНАЛ СОБЫТИЙ (последние 5)", BAR_SINGLE]
    if section_errors.get("events"):
        lines.append(f"  ошибка чтения ({section_errors['events']})")
    elif not events:
        lines.append("  нет событий")
    else:
        for event in events:
            lines.append(compact_audit_line(event))

    lines += ["", BAR_DOUBLE, ""]
    return "\n".join(lines)


def _libvirt_label(raw: Any) -> str:
    text = str(raw or "—")
    if text.lower().startswith("libvirt-"):
        return text[8:]
    return text


def _fetch_host_networks(insp: InspectorBase, host_id: Any) -> list[dict[str, Any]]:
    params = {"host_id": host_id}
    try:
        return insp.fetch_all(
            """
            SELECT name, mac_addr, addr, subnet, gateway, mtu, speed,
                   is_bond, bond_name, vlan_id, network_name
            FROM vds_interface
            WHERE vds_id = CAST(:host_id AS uuid) AND name != 'lo'
            ORDER BY name
            """,
            params,
        )
    except DataLoadError as exc:
        if not should_retry_narrow_sql(exc):
            raise
        return insp.fetch_all(
            """
            SELECT name, mac_addr, addr, subnet, gateway, mtu, speed,
                   is_bond, bond_name, vlan_id
            FROM vds_interface
            WHERE vds_id = CAST(:host_id AS uuid) AND name != 'lo'
            ORDER BY name
            """,
            params,
        )


_TOPOLOGY_MAX_LEN = 120


def _json_cell(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _topology_label(value: Any) -> str | None:
    dumped = _json_cell(value)
    if dumped is None:
        return None
    if len(dumped) <= _TOPOLOGY_MAX_LEN:
        return dumped
    if isinstance(value, dict):
        sockets = value.get("sockets")
        if isinstance(sockets, list):
            return f"sockets: {len(sockets)}"
        return f"keys: {len(value)}"
    if isinstance(value, list):
        return f"items: {len(value)}"
    return dumped[: _TOPOLOGY_MAX_LEN - 3] + "..."


def _fetch_host_engine8(insp: InspectorBase, host_id: Any) -> dict[str, str]:
    try:
        row = insp.fetch_one(
            """
            SELECT cpu_topology, ovn_configured, vdsm_cpus_affinity
            FROM vds_dynamic
            WHERE vds_id = CAST(:host_id AS uuid)
            """,
            {"host_id": host_id},
        )
    except DataLoadError as exc:
        if not should_retry_narrow_sql(exc):
            raise
        return {}
    if not row:
        return {}
    extra: dict[str, str] = {}
    topology = _topology_label(row.get("cpu_topology"))
    if topology is not None:
        extra["cpu_topology"] = topology
    if row.get("ovn_configured") is not None:
        extra["ovn_configured"] = _yes_no(row.get("ovn_configured"))
    affinity = row.get("vdsm_cpus_affinity")
    if affinity not in (None, ""):
        extra["vdsm_cpus_affinity"] = str(affinity)
    return extra


def get_host_inspector_report(
    db_name: str, host_id: str, *, release_key: str | None = None
) -> dict:
    """Возвращает словарь с отчетом и навигационными данными."""
    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)

            host = insp.fetch_one(
                """
                SELECT
                    s.vds_id, s.vds_name, s.host_name, s.cluster_id,
                    s._create_date, s._update_date,
                    d.status, d.cpu_sockets, d.cpu_cores, d.cpu_threads, d.cpu_model,
                    d.physical_mem_mb, d.mem_commited, d.vm_active,
                    d.software_version, d.host_os, d.kvm_version,
                    d.kernel_version, d.libvirt_version, d.pretty_name,
                    d.kdump_status as kdump_code,
                    c.name as cluster_name, sp.name as dc_name, sp.id as storage_pool_id,
                    (s.vds_id = sp.spm_vds_id) AS is_spm
                FROM vds_static s
                JOIN vds_dynamic d ON s.vds_id = d.vds_id
                LEFT JOIN cluster c ON s.cluster_id = c.cluster_id
                LEFT JOIN storage_pool sp ON c.storage_pool_id = sp.id
                WHERE s.vds_id::text = :host_id LIMIT 1
                """,
                {"host_id": host_id},
            )

            if not host:
                return {"error": "Хост не найден.", "report_text": "", "nav_data": {}}

            section_errors: dict[str, str] = {}
            networks: list[dict[str, Any]] = []
            events: list[dict[str, Any]] = []
            engine8: dict[str, str] = {}

            if release_key != "7.3":
                try:
                    engine8 = _fetch_host_engine8(insp, host["vds_id"])
                except DataLoadError as exc:
                    section_errors["engine8"] = str(exc)

            try:
                networks = _fetch_host_networks(insp, host["vds_id"])
            except DataLoadError as exc:
                section_errors["networks"] = str(exc)

            try:
                events = insp.fetch_all(
                    """
                    SELECT log_time, log_type_name, user_name, message
                    FROM audit_log
                    WHERE vds_id = CAST(:host_id AS uuid) OR vds_name = :host_name
                    ORDER BY log_time DESC LIMIT 5
                    """,
                    {"host_id": host["vds_id"], "host_name": host["vds_name"]},
                )
            except DataLoadError as exc:
                section_errors["events"] = str(exc)

            kdump_label = KDUMP_MAP.get(host["kdump_code"], f"Code {host['kdump_code']}")
            payload = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "header": {
                    "name": host["vds_name"],
                    "id": host["vds_id"],
                    "fqdn": host["host_name"],
                    "cluster": host["cluster_name"] or "—",
                    "dc": host["dc_name"] or "—",
                    "created": _fmt_date(host["_create_date"]),
                    "updated": _fmt_date(host["_update_date"]),
                },
                "metrics": {
                    "status": HOST_STATUS_MAP.get(host["status"], f"Code {host['status']}"),
                    "kdump": kdump_label,
                    "spm": "да" if host["is_spm"] else "нет",
                    "cpu": _cpu_label(
                        host["cpu_sockets"], host["cpu_cores"], host["cpu_threads"]
                    ),
                    "cpu_model": host["cpu_model"] or "—",
                    "ram": _ram_label(host["physical_mem_mb"], host["mem_commited"]),
                    "vm_active": host["vm_active"] if host["vm_active"] is not None else 0,
                },
                "versions": {
                    "os": host["pretty_name"] or host["host_os"] or "—",
                    "kernel": host["kernel_version"] or "—",
                    "vdsm": host["software_version"] or "—",
                    "libvirt": _libvirt_label(host["libvirt_version"]),
                    "kvm": host["kvm_version"] or "—",
                },
                "networks": networks,
                "events": events,
                "engine8": engine8,
                "section_errors": section_errors,
                "nav_data": {
                    "cluster_id": host["cluster_id"],
                    "cluster_name": host["cluster_name"],
                    "dc_name": host["dc_name"],
                },
            }
            payload["report_text"] = format_host_report(payload)
            return payload

    except DataLoadError as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

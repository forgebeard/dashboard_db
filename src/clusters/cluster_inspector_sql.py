# src/clusters/cluster_inspector_sql.py
"""Диагностический отчёт по кластеру (Cluster-Inspector)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from core.constants import (
    ARCHITECTURE_MAP,
    BIOS_TYPE_MAP,
    HOST_STATUS_MAP,
    MIGRATE_ON_ERROR_MAP,
    VM_STATUS_UP,
)
from core.inspector_base import InspectorBase
from core.report_text import BAR_DOUBLE, BAR_SINGLE
from core.report_text import _kv as _kv_core


def _fmt_size_mb(mb: Any) -> str:
    if mb in (None, ""):
        return "—"
    try:
        return f"{round(float(mb) / 1024, 1)} ГБ"
    except (ValueError, TypeError):
        return "—"


def _kv(label: str, value: Any, width: int = 18) -> str:
    return _kv_core(label, value, width)


def _on_off(flag: Any) -> str:
    if flag in (True, 1, "1", "t", "true", "True"):
        return "вкл"
    if flag in (False, 0, "0", "f", "false", "False"):
        return "выкл"
    return "—"


def _map_code(mapping: dict[int, str], code: Any) -> str:
    if code is None or code == "":
        return "—"
    try:
        key = int(code)
    except (TypeError, ValueError):
        return str(code)
    return mapping.get(key, f"Code {code}")


def _parse_policy_props(raw: Any) -> list[tuple[str, str]]:
    if raw in (None, ""):
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    items: list[tuple[str, str]] = []
    for key, value in sorted(data.items()):
        items.append((str(key), str(value)))
    return items


def _truthy(flag: Any) -> bool:
    return flag in (True, 1, "1", "t", "true", "True")


def format_cluster_report(payload: dict[str, Any]) -> str:
    header = payload.get("header") or {}
    resources = payload.get("resources") or {}
    policy = payload.get("policy") or {}
    hosts = payload.get("hosts") or []
    affinity = payload.get("affinity") or []
    section_errors = payload.get("section_errors") or {}
    generated_at = payload.get("generated_at") or "—"

    lines = [
        BAR_DOUBLE,
        f"  Cluster-Inspector                                  {generated_at}",
        BAR_DOUBLE,
        "",
        "СВЕДЕНИЯ О КЛАСТЕРЕ",
        BAR_SINGLE,
        _kv("Имя", header.get("name")),
        _kv("UUID", header.get("id")),
        _kv("Дата-центр", header.get("dc")),
        _kv("Совместимость", header.get("compat")),
        _kv("CPU", header.get("cpu")),
        _kv("Архитектура", header.get("architecture")),
        _kv("Машина", header.get("machine")),
        _kv("BIOS", header.get("bios")),
        _kv("MAC-пул", header.get("mac_pool")),
        _kv("Планировщик", header.get("scheduler")),
        "",
        "РЕСУРСЫ",
        BAR_SINGLE,
        _kv("ВМ", resources.get("vms")),
        _kv("RAM / CPU", resources.get("capacity")),
        _kv("Overcommit", resources.get("overcommit")),
        "",
        "ПОЛИТИКА",
        BAR_SINGLE,
    ]

    props = policy.get("properties") or []
    if props:
        for key, value in props:
            lines.append(_kv(key, value))
    lines += [
        _kv("При ошибке хоста", policy.get("migrate_on_error")),
        _kv("Balloon / KSM", policy.get("memory")),
        _kv("HA reservation", policy.get("ha_reservation")),
        _kv("Fencing", policy.get("fencing")),
    ]
    for extra in policy.get("fencing_extra") or []:
        lines.append(_kv(extra[0], extra[1]))

    lines += ["", "ХОСТЫ", BAR_SINGLE]
    if section_errors.get("hosts"):
        lines.append(f"  ошибка чтения ({section_errors['hosts']})")
    elif not hosts:
        lines.append("  нет хостов")
    else:
        for host in hosts:
            name = str(host.get("name") or "—")
            status = str(host.get("status") or "—")
            lines.append(f"  {name:<40}{status}")

    if section_errors.get("affinity"):
        lines += ["", "АФФИННОСТЬ", BAR_SINGLE]
        lines.append(f"  ошибка чтения ({section_errors['affinity']})")
    elif affinity:
        lines += ["", "АФФИННОСТЬ", BAR_SINGLE]
        for group in affinity:
            lines.append(_kv("Группа", group.get("name")))
            lines.append(_kv("VM", group.get("vm_rule")))
            lines.append(_kv("Host", group.get("host_rule")))
            members = group.get("members") or []
            if members:
                lines.append(_kv("Члены", ", ".join(members)))
            lines.append("")

    lines += ["", BAR_DOUBLE, ""]
    return "\n".join(lines)


def _group_affinity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        name = row.get("name")
        if current is None or current.get("name") != name:
            vm_kind = "Positive" if row.get("vm_positive") else "Negative"
            enforcing = "Enforced" if row.get("vm_enforcing") else "Soft"
            host_kind = "Positive" if row.get("vds_positive") else "Negative"
            current = {
                "name": name,
                "vm_rule": f"{vm_kind} ({enforcing})",
                "host_rule": host_kind,
                "members": [],
            }
            groups.append(current)
        bits = []
        if row.get("vm_name"):
            bits.append(str(row["vm_name"]))
        if row.get("vds_name"):
            bits.append(str(row["vds_name"]))
        if bits and current is not None:
            current["members"].append(" / ".join(bits))
    return groups


def get_cluster_inspector_report(db_name: str, cluster_id: str) -> dict:
    cluster_search = str(cluster_id).strip().lower()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)
            cluster = insp.fetch_one(
                """
                SELECT
                    c.cluster_id, c.name, c.compatibility_version, c.cpu_name,
                    c.architecture, c.emulated_machine, c.bios_type,
                    c.max_vds_memory_over_commit,
                    c.enable_balloon, c.enable_ksm, c.ha_reservation,
                    c.fencing_enabled, c.skip_fencing_if_sd_active,
                    c.skip_fencing_if_connectivity_broken,
                    c.hosts_with_broken_connectivity_threshold,
                    c.migrate_on_error, c.cluster_policy_custom_properties,
                    sp.name AS datacenter_name,
                    cp.name AS scheduler_policy,
                    mp.name AS mac_pool
                FROM cluster c
                LEFT JOIN storage_pool sp ON c.storage_pool_id = sp.id
                LEFT JOIN cluster_policies cp ON c.cluster_policy_id = cp.id
                LEFT JOIN mac_pools mp ON c.mac_pool_id = mp.id
                WHERE c.cluster_id::text = :cluster_id
                LIMIT 1
                """,
                {"cluster_id": cluster_search},
            )
            if not cluster:
                return {"error": "Кластер не найден.", "report_text": "", "nav_data": {}}

            section_errors: dict[str, str] = {}
            host_rows: list[dict[str, Any]] = []
            vm_row: dict[str, Any] | None = None
            affinity_rows: list[dict[str, Any]] = []
            params = {"cluster_id": cluster_search}

            try:
                host_rows = insp.fetch_all(
                    """
                    SELECT v.vds_name, v.status AS host_status_code,
                           v.physical_mem_mb, v.cpu_cores
                    FROM vds v
                    WHERE v.cluster_id::text = :cluster_id
                    ORDER BY v.vds_name
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["hosts"] = str(exc)

            try:
                vm_row = insp.fetch_one(
                    f"""
                    SELECT
                        COUNT(*) AS vms,
                        COUNT(*) FILTER (WHERE d.status = {VM_STATUS_UP}) AS vm_up
                    FROM vm_static s
                    LEFT JOIN vm_dynamic d ON s.vm_guid = d.vm_guid
                    WHERE s.cluster_id::text = :cluster_id
                      AND s.entity_type = 'VM'
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["vms"] = str(exc)

            try:
                affinity_rows = insp.fetch_all(
                    """
                    SELECT ag.name, ag.vm_positive, ag.vm_enforcing,
                           ag.vds_positive, ag.vds_enforcing,
                           vs.vm_name, hs.vds_name
                    FROM affinity_groups ag
                    LEFT JOIN affinity_group_members agm
                           ON ag.id = agm.affinity_group_id
                    LEFT JOIN vm_static vs ON vs.vm_guid = agm.vm_id
                    LEFT JOIN vds_static hs ON hs.vds_id = agm.vds_id
                    WHERE ag.cluster_id::text = :cluster_id
                    ORDER BY ag.name, vs.vm_name, hs.vds_name
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["affinity"] = str(exc)

            ram_mb = 0
            cores = 0
            hosts = []
            for row in host_rows:
                hosts.append(
                    {
                        "name": row.get("vds_name"),
                        "status": HOST_STATUS_MAP.get(
                            row.get("host_status_code"),
                            f"Code {row.get('host_status_code')}",
                        ),
                    }
                )
                try:
                    ram_mb += float(row.get("physical_mem_mb") or 0)
                except (TypeError, ValueError):
                    pass
                try:
                    cores += int(row.get("cpu_cores") or 0)
                except (TypeError, ValueError):
                    pass

            vms_total = int((vm_row or {}).get("vms") or 0)
            vms_up = int((vm_row or {}).get("vm_up") or 0)
            over = cluster.get("max_vds_memory_over_commit")
            over_label = f"{over}%" if over not in (None, "") else "—"

            fencing_extra: list[tuple[str, str]] = []
            if _truthy(cluster.get("skip_fencing_if_sd_active")):
                fencing_extra.append(("Skip if SD active", "вкл"))
            if _truthy(cluster.get("skip_fencing_if_connectivity_broken")):
                thresh = cluster.get("hosts_with_broken_connectivity_threshold")
                label = "вкл" if thresh in (None, "") else f"вкл ({thresh}%)"
                fencing_extra.append(("Skip if connectivity", label))

            payload = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "header": {
                    "name": cluster.get("name"),
                    "id": cluster.get("cluster_id"),
                    "dc": cluster.get("datacenter_name") or "—",
                    "compat": cluster.get("compatibility_version") or "—",
                    "cpu": cluster.get("cpu_name") or "—",
                    "architecture": _map_code(
                        ARCHITECTURE_MAP, cluster.get("architecture")
                    ),
                    "machine": cluster.get("emulated_machine") or "—",
                    "bios": _map_code(BIOS_TYPE_MAP, cluster.get("bios_type")),
                    "mac_pool": cluster.get("mac_pool") or "—",
                    "scheduler": cluster.get("scheduler_policy") or "—",
                },
                "resources": {
                    "vms": f"{vms_up} Up / {vms_total}",
                    "capacity": f"{_fmt_size_mb(ram_mb)}  /  {cores} ядер",
                    "overcommit": over_label,
                },
                "policy": {
                    "properties": _parse_policy_props(
                        cluster.get("cluster_policy_custom_properties")
                    ),
                    "migrate_on_error": _map_code(
                        MIGRATE_ON_ERROR_MAP, cluster.get("migrate_on_error")
                    ),
                    "memory": (
                        f"{_on_off(cluster.get('enable_balloon'))} / "
                        f"{_on_off(cluster.get('enable_ksm'))}"
                    ),
                    "ha_reservation": _on_off(cluster.get("ha_reservation")),
                    "fencing": _on_off(cluster.get("fencing_enabled")),
                    "fencing_extra": fencing_extra,
                },
                "hosts": hosts,
                "affinity": _group_affinity(affinity_rows),
                "section_errors": section_errors,
                "nav_data": {
                    "cluster_id": cluster.get("cluster_id"),
                    "cluster_name": cluster.get("name"),
                    "datacenter_name": cluster.get("datacenter_name"),
                    "host_count": len(hosts),
                },
            }
            if section_errors.get("vms"):
                payload["resources"]["vms"] = f"ошибка чтения ({section_errors['vms']})"
            payload["report_text"] = format_cluster_report(payload)
            return payload
    except Exception as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

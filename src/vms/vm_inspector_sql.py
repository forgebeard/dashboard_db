# src/vms/vm_inspector_sql.py
"""
Диагностический отчёт по ВМ (VM-Inspector).
Сбор данных отдельно от вёрстки — как Host-Inspector.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from core.constants import (
    BIOS_TYPE_MAP,
    IMAGE_STATUS_MAP,
    VM_STATUS_MAP,
    VM_STATUS_UP,
)
from core.exceptions import DataLoadError, should_retry_narrow_sql
from core.inspector_base import InspectorBase
from core.report_text import BAR_DOUBLE, BAR_SINGLE, _kv, _kv_at, _yes_no

VOLUME_TYPE_MAP = {0: "Unassigned", 1: "Preallocated", 2: "Sparse"}
VOLUME_FORMAT_MAP = {1: "RAW", 4: "COW"}
GUEST_AGENT_MAP = {0: "нет", 1: "есть", 2: "обновить"}

AUDIT_TYPE_LABELS = {
    "VM_CONSOLE_DISCONNECTED": "console disconnected",
    "VM_CONSOLE_CONNECTED": "console connected",
    "VM_SET_TICKET": "console ticket",
    "USER_RESET_VM": "VM reset",
    "USER_RUN_VM": "VM start",
    "USER_STOP_VM": "VM stop",
    "USER_ATTACH_DISK_TO_VM": "disk attached",
    "USER_CREATE_SNAPSHOT": "snapshot create",
    "USER_REMOVE_SNAPSHOT": "snapshot remove",
}

_ATTACH_DISK_RE = re.compile(
    r"Disk (\S+) was successfully attached to VM (\S+)", re.IGNORECASE
)
_VM_NAME_RE = re.compile(r"\bVM (\S+)")


def _fmt_size_mb(mb: Any) -> str:
    if mb is None:
        return "—"
    try:
        return f"{round(float(mb) / 1024, 1)} ГБ"
    except (ValueError, TypeError):
        return f"{mb} MB"


def _fmt_size_bytes(raw: Any) -> str:
    if raw in (None, ""):
        return "—"
    try:
        return f"{round(float(raw) / (1024**3), 1)} ГБ"
    except (ValueError, TypeError):
        return "—"


def _safe_date(dt: Any) -> datetime | None:
    if not dt:
        return None
    return dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt


def _fmt_date(dt: Any) -> str:
    if not dt:
        return "—"
    parsed = _safe_date(dt)
    if parsed is None:
        return "—"
    return parsed.strftime("%d.%m.%Y %H:%M")


def _fmt_ts(dt: Any) -> str:
    if not dt:
        return "—"
    parsed = _safe_date(dt)
    if parsed is None:
        return "—"
    return parsed.strftime("%d.%m.%Y %H:%M:%S")


NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _norm_id(raw: Any) -> str:
    if raw in (None, ""):
        return ""
    return str(raw).strip().lower()


def _is_nil_id(raw: Any) -> bool:
    return _norm_id(raw) in ("", NIL_UUID)


def _id_text(raw: Any) -> str | None:
    if raw in (None, ""):
        return None
    return str(raw).strip()


def _image_status(code: Any) -> str:
    if code is None:
        return "—"
    return IMAGE_STATUS_MAP.get(code, f"Code {code}")


def _volume_bit(layer: dict[str, Any]) -> str:
    vol = VOLUME_TYPE_MAP.get(layer.get("volume_type"), "")
    fmt = VOLUME_FORMAT_MAP.get(layer.get("volume_format"), "")
    return " ".join(part for part in (vol, fmt) if part)


def order_layers_by_parent(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Корень → лист по parentid внутри каждого диска. Циклы — в хвост."""
    if not layers:
        return []

    aliases: list[Any] = []
    by_disk: dict[Any, list[dict[str, Any]]] = {}
    for layer in layers:
        alias = layer.get("disk_alias")
        if alias not in by_disk:
            aliases.append(alias)
            by_disk[alias] = []
        by_disk[alias].append(layer)

    ordered: list[dict[str, Any]] = []
    for alias in aliases:
        ordered.extend(_order_disk_layers(by_disk[alias]))
    return ordered


def _order_disk_layers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    id_set = {_norm_id(row.get("image_guid")) for row in rows}
    id_set.discard("")
    children: dict[str, list[dict[str, Any]]] = {gid: [] for gid in id_set}
    roots: list[dict[str, Any]] = []
    for row in rows:
        gid = _norm_id(row.get("image_guid"))
        pid = _norm_id(row.get("parentid"))
        if gid and pid and pid != NIL_UUID and pid in id_set:
            children[pid].append(row)
        else:
            roots.append(row)

    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    queue = list(roots)
    while queue:
        node = queue.pop(0)
        marker = id(node)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(node)
        gid = _norm_id(node.get("image_guid"))
        if gid:
            queue.extend(children.get(gid, []))

    for row in rows:
        if id(row) not in seen:
            out.append(row)
    return out


def _cpu_label(sockets: Any, cores: Any, threads: Any) -> str:
    sock = sockets if sockets is not None else "—"
    core = cores if cores is not None else "—"
    line = f"{sock} сокета × {core} ядер"
    if threads not in (None, "", 0, "0"):
        line += f"    потоки: {threads}"
    return line


def _os_label(os_name: Any, os_code: Any) -> str:
    name = str(os_name).strip() if os_name not in (None, "") else ""
    if name:
        return name
    if os_code in (None, ""):
        return "—"
    return f"OS {os_code}"


def guest_os_label(row: dict[str, Any] | None) -> str | None:
    data = row or {}
    dist = str(data.get("guestos_distribution") or "").strip()
    ver = str(data.get("guestos_version") or "").strip()
    if dist and ver:
        return f"{dist} {ver}"
    if dist:
        return dist
    fallback = str(data.get("guest_os") or "").strip()
    return fallback or None


def layer_snap_label(layer: dict[str, Any]) -> str:
    """Только uuid снапшота. Пустой id → «—»."""
    snap_id = layer.get("vm_snapshot_id")
    if _is_nil_id(snap_id):
        return "—"
    return str(snap_id)


def layer_note(layer: dict[str, Any]) -> str | None:
    parts: list[str] = []
    snap_type = layer.get("snapshot_type")
    if snap_type not in (None, ""):
        parts.append(str(snap_type))
    desc = layer.get("snap_desc")
    if desc not in (None, ""):
        parts.append(str(desc))
    return "    ".join(parts) if parts else None


def snapshot_type_label(raw: Any) -> str:
    if raw in (None, ""):
        return "—"
    return str(raw)


def _layers_for_snapshot(
    layers: list[dict[str, Any]], snapshot_id: Any
) -> list[str]:
    want = _norm_id(snapshot_id)
    if not want:
        return []
    guids: list[str] = []
    for layer in layers:
        if _norm_id(layer.get("vm_snapshot_id")) != want:
            continue
        guid = layer.get("image_guid")
        if guid not in (None, ""):
            guids.append(str(guid))
    return guids


def _agent_label(code: Any) -> str:
    if code in (None, ""):
        return "—"
    try:
        key = int(code)
    except (TypeError, ValueError):
        return str(code)
    return GUEST_AGENT_MAP.get(key, f"Code {key}")


def _uptime_label(status_code: Any, boot_time: Any, now: datetime) -> str:
    if status_code != VM_STATUS_UP:
        return "—"
    started = _safe_date(boot_time)
    if not started:
        return "—"
    delta = now - started
    return f"{delta.days}д {delta.seconds // 3600}ч {(delta.seconds % 3600) // 60}м"


def _norm_mac(mac: Any) -> str:
    return str(mac or "").strip().lower()


def merge_guest_ips(
    nics: list[dict[str, Any]], guest_ifaces: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_mac: dict[str, dict[str, Any]] = {}
    for row in guest_ifaces:
        mac = _norm_mac(row.get("mac_address"))
        if mac:
            by_mac[mac] = row
    merged: list[dict[str, Any]] = []
    for nic in nics:
        item = dict(nic)
        guest = by_mac.get(_norm_mac(nic.get("mac_addr")))
        item["ipv4"] = guest.get("ipv4_addresses") if guest else None
        merged.append(item)
    return merged


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


def format_vm_report(payload: dict[str, Any]) -> str:
    """Собирает текстовый отчёт по согласованному макету."""
    header = payload.get("header") or {}
    metrics = payload.get("metrics") or {}
    disks = payload.get("disks") or []
    layers = payload.get("layers") or []
    snapshots = payload.get("snapshots") or []
    nics = payload.get("networks") or []
    events = payload.get("events") or []
    section_errors = payload.get("section_errors") or {}
    generated_at = payload.get("generated_at") or "—"

    lines = [
        BAR_DOUBLE,
        f"  VM-Inspector                                     {generated_at}",
        BAR_DOUBLE,
        "",
        "СВЕДЕНИЯ О ВМ",
        BAR_SINGLE,
        _kv("Имя", header.get("name")),
        _kv("UUID", header.get("id")),
        _kv("Описание", header.get("description")),
    ]
    comment = header.get("comment")
    if comment not in (None, ""):
        lines.append(_kv("Комментарий", comment))
    lines += [
        _kv("ОС", header.get("os")),
        _kv("Гостевая ОС", header.get("guest_os")),
        _kv("Шаблон", header.get("template")),
        _kv("BIOS", header.get("bios")),
        _kv("Кластер", header.get("cluster")),
        _kv("Дата-центр", header.get("dc")),
        _kv("Хост", header.get("host")),
        _kv("Создан", header.get("created")),
        _kv("Обновлён", header.get("updated")),
        "",
        "РЕСУРСЫ",
        BAR_SINGLE,
        _kv("Статус", metrics.get("status")),
        _kv("Uptime", metrics.get("uptime")),
        _kv("CPU", metrics.get("cpu")),
        _kv("RAM", metrics.get("ram")),
        _kv("IP", metrics.get("vm_ip")),
        _kv("QEMU agent", metrics.get("qemu_agent")),
        _kv("oVirt agent", metrics.get("ovirt_agent")),
        "",
    ]

    engine = payload.get("engine_compat") or {}
    engine_err = section_errors.get("engine_compat")
    if engine_err or engine:
        rel = engine.get("release")
        if engine_err:
            heading = "РЕД ВИРТ 8"
        elif rel == "7.3":
            heading = "РЕД ВИРТ 7.3"
        else:
            heading = "РЕД ВИРТ 8"
        lines += [
            heading,
            BAR_SINGLE,
        ]
        if engine_err:
            lines.append(f"  ошибка чтения ({engine_err})")
        else:
            if "virtio_scsi" in engine:
                if rel == "7.3":
                    lines.append(
                        _kv("virtio-scsi multi-queue", _yes_no(engine["virtio_scsi"]))
                    )
                else:
                    lines.append(_kv("virtio-scsi queues", engine["virtio_scsi"]))
            if "cpu_pinning_policy" in engine:
                lines.append(_kv("CPU pinning", engine["cpu_pinning_policy"]))
            if "parallel_migrations" in engine:
                lines.append(_kv("Паралл. миграции", engine["parallel_migrations"]))
        lines.append("")

    lines += [
        "ДИСКИ",
        BAR_SINGLE,
    ]

    if section_errors.get("disks"):
        lines.append(f"  ошибка чтения ({section_errors['disks']})")
    elif not disks:
        lines.append("  нет дисков")
    else:
        for disk in disks:
            lines.append(_kv_at("    ", "имя", disk.get("disk_alias")))
            lines.append(_kv_at("    ", "UUID", disk.get("disk_id")))
            lines.append(
                _kv_at(
                    "    ",
                    "Шина",
                    disk.get("disk_interface") or disk.get("bus") or "—",
                )
            )
            lines.append(_kv_at("    ", "Boot", _yes_no(disk.get("is_boot"))))
            lines.append(_kv_at("    ", "Подключён", _yes_no(disk.get("is_plugged"))))
            lines.append(
                _kv_at("    ", "Вирт. размер", _fmt_size_bytes(disk.get("virt_bytes")))
            )
            lines.append(_kv_at("    ", "Хранилище", disk.get("storage_name") or "—"))
            lines.append(
                _kv_at("    ", "Активный слой", disk.get("active_image") or "—")
            )
            lines.append(_kv_at("    ", "Статус", _image_status(disk.get("imagestatus"))))
            lines.append("")

    lines += ["", "СЛОИ", BAR_SINGLE]
    if section_errors.get("layers"):
        lines.append(f"  ошибка чтения ({section_errors['layers']})")
    elif not layers:
        lines.append("  нет слоёв")
    else:
        for layer in order_layers_by_parent(layers):
            lines.append(_kv_at("    ", "диск", layer.get("disk_alias")))
            lines.append(_kv_at("    ", "image_guid", layer.get("image_guid")))
            if layer.get("active"):
                lines.append(_kv_at("    ", "состояние", "active"))
            lines.append(_kv_at("    ", "parentid", _id_text(layer.get("parentid"))))
            lines.append(_kv_at("    ", "it_guid", _id_text(layer.get("it_guid"))))
            lines.append(_kv_at("    ", "статус", _image_status(layer.get("imagestatus"))))
            lines.append(_kv_at("    ", "тип", _volume_bit(layer) or "—"))
            lines.append(_kv_at("    ", "размер", _fmt_size_bytes(layer.get("actual_size"))))
            lines.append(_kv_at("    ", "_create_date", _fmt_ts(layer.get("_create_date"))))
            lines.append(
                _kv_at("    ", "creation_date", _fmt_ts(layer.get("creation_date")))
            )
            lines.append(_kv_at("    ", "_update_date", _fmt_ts(layer.get("_update_date"))))
            lines.append(_kv_at("    ", "снапшот", layer_snap_label(layer)))
            note = layer_note(layer)
            if note:
                lines.append(_kv_at("    ", "заметка", note))
            lines.append("")

    lines += ["", "СНАПШОТЫ", BAR_SINGLE]
    if section_errors.get("snapshots"):
        lines.append(f"  ошибка чтения ({section_errors['snapshots']})")
    elif not snapshots:
        lines.append("  нет снапшотов")
    else:
        for snap in snapshots:
            lines.append(_kv_at("    ", "snapshot_id", snap.get("snapshot_id")))
            lines.append(_kv_at("    ", "тип", snapshot_type_label(snap.get("snapshot_type"))))
            lines.append(_kv_at("    ", "статус", snap.get("status") or "—"))
            lines.append(_kv_at("    ", "дата", _fmt_ts(snap.get("creation_date"))))
            lines.append(_kv_at("    ", "имя", snap.get("description") or "—"))
            linked = _layers_for_snapshot(layers, snap.get("snapshot_id"))
            if not linked:
                lines.append(_kv_at("    ", "слои", "—"))
            elif len(linked) == 1:
                lines.append(_kv_at("    ", "слои", linked[0]))
            else:
                lines.append("    слои:")
                for guid in linked:
                    lines.append(f"      {guid}")
            if snap.get("memory_dump_disk_id") or snap.get("memory_metadata_disk_id"):
                lines.append(_kv_at("    ", "память", "да"))
            lines.append("")

    lines += ["", "СЕТЬ", BAR_SINGLE]
    if section_errors.get("networks"):
        lines.append(f"  ошибка чтения ({section_errors['networks']})")
    elif not nics:
        lines.append("  нет интерфейсов")
    else:
        for nic in nics:
            extra = []
            mac = nic.get("mac_addr")
            if mac:
                extra.append(f"MAC {mac}")
            net = nic.get("net_name")
            if net:
                extra.append(str(net))
            tail = ("    " + "    ".join(extra)) if extra else ""
            lines.append(
                f"    {nic.get('name') or '—'!s:<14}{nic.get('ipv4') or '—'}{tail}"
            )

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


def _fetch_vm_engine_compat(insp: InspectorBase, vm_guid: Any) -> dict[str, Any]:
    params = {"vm_guid": vm_guid}
    try:
        row = insp.fetch_one(
            """
            SELECT virtio_scsi_multi_queues, cpu_pinning_policy, parallel_migrations
            FROM vm_static
            WHERE vm_guid = :vm_guid
            """,
            params,
        )
        extra: dict[str, Any] = {}
        if row:
            if row.get("virtio_scsi_multi_queues") is not None:
                extra["virtio_scsi"] = row["virtio_scsi_multi_queues"]
            if row.get("cpu_pinning_policy") is not None:
                extra["cpu_pinning_policy"] = row["cpu_pinning_policy"]
            if row.get("parallel_migrations") is not None:
                extra["parallel_migrations"] = row["parallel_migrations"]
        if extra:
            extra["release"] = "8"
        return extra
    except DataLoadError as exc:
        if not should_retry_narrow_sql(exc):
            raise
    row = insp.fetch_one(
        """
        SELECT virtio_scsi_multi_queues_enabled
        FROM vm_static
        WHERE vm_guid = :vm_guid
        """,
        params,
    )
    if not row or row.get("virtio_scsi_multi_queues_enabled") is None:
        return {}
    return {"release": "7.3", "virtio_scsi": row["virtio_scsi_multi_queues_enabled"]}


def get_vm_inspector_report(
    db_name: str, vm_guid: str, *, release_key: str | None = None
) -> dict:
    """Возвращает словарь с отчетом и навигационными данными."""
    vm_search = str(vm_guid).strip().lower()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)

            vm = insp.fetch_one(
                """
                SELECT
                    v.vm_guid, v.vm_name, v.description, v.free_text_comment,
                    v._create_date, v._update_date, v.os, v.vmt_guid, v.bios_type,
                    v.num_of_sockets, v.cpu_per_socket, v.threads_per_cpu, v.mem_size_mb,
                    v.cluster_id::text AS cluster_id,
                    o.os_name,
                    tpl.vm_name AS template_name,
                    d.status AS vm_status_code, d.run_on_vds, d.boot_time, d.vm_ip,
                    d.guest_os, d.guestos_distribution, d.guestos_version,
                    d.qemu_guest_agent_status, d.ovirt_guest_agent_status,
                    c.name AS cluster_name, dc.name AS dc_name,
                    h.vds_name AS host_name, h.vds_id::text AS vds_id
                FROM vm_static v
                LEFT JOIN vm_dynamic d ON v.vm_guid = d.vm_guid
                LEFT JOIN dwh_osinfo o ON o.os_id = v.os
                LEFT JOIN vm_static tpl ON tpl.vm_guid = v.vmt_guid
                LEFT JOIN cluster c ON v.cluster_id = c.cluster_id
                LEFT JOIN storage_pool dc ON c.storage_pool_id = dc.id
                LEFT JOIN vds_static h ON d.run_on_vds = h.vds_id
                WHERE v.vm_guid::text = :vm_search
                LIMIT 1
                """,
                {"vm_search": vm_search},
            )

            if not vm:
                return {"error": "ВМ не найдена.", "report_text": "", "nav_data": {}}

            section_errors: dict[str, str] = {}
            disks: list[dict[str, Any]] = []
            layers: list[dict[str, Any]] = []
            snapshots: list[dict[str, Any]] = []
            nics: list[dict[str, Any]] = []
            guest_ifaces: list[dict[str, Any]] = []
            events: list[dict[str, Any]] = []
            params = {"vm_guid": vm["vm_guid"]}

            try:
                disks = insp.fetch_all(
                    """
                    SELECT
                        bd.disk_alias,
                        bd.disk_id::text,
                        dve.is_boot,
                        dve.disk_interface,
                        vd.is_plugged,
                        vd.device AS bus,
                        i.image_guid::text AS active_image,
                        i.size AS virt_bytes,
                        i.imagestatus,
                        sd.storage_name
                    FROM vm_device vd
                    JOIN base_disks bd ON bd.disk_id = vd.device_id
                    LEFT JOIN disk_vm_element dve
                           ON dve.disk_id = bd.disk_id AND dve.vm_id = vd.vm_id
                    LEFT JOIN images i
                           ON i.image_group_id = bd.disk_id AND i.active IS TRUE
                    LEFT JOIN image_storage_domain_map m ON m.image_id = i.image_guid
                    LEFT JOIN storage_domain_static sd ON sd.id = m.storage_domain_id
                    WHERE vd.vm_id = :vm_guid AND vd.type = 'disk'
                    ORDER BY bd.disk_alias
                    """,
                    params,
                )
            except DataLoadError as exc:
                section_errors["disks"] = str(exc)

            try:
                layers = insp.fetch_all(
                    """
                    SELECT
                        bd.disk_alias,
                        i.image_guid::text,
                        i.parentid::text,
                        i.it_guid::text,
                        i.active,
                        i.imagestatus,
                        i.volume_type,
                        i.volume_format,
                        i.vm_snapshot_id::text,
                        s.description AS snap_desc,
                        s.snapshot_type,
                        i.creation_date,
                        i._create_date,
                        i._update_date,
                        did.actual_size
                    FROM vm_device vd
                    JOIN base_disks bd ON bd.disk_id = vd.device_id
                    JOIN images i ON i.image_group_id = bd.disk_id
                    LEFT JOIN snapshots s ON s.snapshot_id = i.vm_snapshot_id
                    LEFT JOIN disk_image_dynamic did ON did.image_id = i.image_guid
                    WHERE vd.vm_id = :vm_guid AND vd.type = 'disk'
                    ORDER BY bd.disk_alias, i.creation_date
                    """,
                    params,
                )
            except DataLoadError as exc:
                section_errors["layers"] = str(exc)

            try:
                snapshots = insp.fetch_all(
                    """
                    SELECT
                        s.snapshot_id::text,
                        s.snapshot_type,
                        s.status,
                        s.description,
                        s.creation_date,
                        s.memory_dump_disk_id,
                        s.memory_metadata_disk_id,
                        COUNT(i.image_guid) AS layer_count
                    FROM snapshots s
                    LEFT JOIN images i ON i.vm_snapshot_id = s.snapshot_id
                    WHERE s.vm_id = :vm_guid
                    GROUP BY
                        s.snapshot_id, s.snapshot_type, s.status, s.description,
                        s.creation_date, s.memory_dump_disk_id, s.memory_metadata_disk_id
                    ORDER BY s.creation_date DESC
                    """,
                    params,
                )
            except DataLoadError as exc:
                section_errors["snapshots"] = str(exc)

            try:
                nics = insp.fetch_all(
                    """
                    SELECT vni.name, vni.mac_addr, n.name AS net_name
                    FROM vm_interface vni
                    LEFT JOIN vnic_profiles vp ON vni.vnic_profile_id = vp.id
                    LEFT JOIN network n ON vp.network_id = n.id
                    WHERE vni.vm_guid = :vm_guid
                    ORDER BY vni.name
                    """,
                    params,
                )
                guest_ifaces = insp.fetch_all(
                    """
                    SELECT interface_name, mac_address, ipv4_addresses
                    FROM vm_guest_agent_interfaces
                    WHERE vm_id = :vm_guid
                    """,
                    params,
                )
                nics = merge_guest_ips(nics, guest_ifaces)
            except DataLoadError as exc:
                section_errors["networks"] = str(exc)
                nics = []

            try:
                events = insp.fetch_all(
                    """
                    SELECT log_time, log_type_name, user_name, message
                    FROM audit_log
                    WHERE vm_id = :vm_guid OR vm_name = :vm_name
                    ORDER BY log_time DESC
                    LIMIT 5
                    """,
                    {"vm_guid": vm["vm_guid"], "vm_name": vm["vm_name"]},
                )
            except DataLoadError as exc:
                section_errors["events"] = str(exc)

            engine_compat: dict[str, Any] = {}
            if release_key != "7.3":
                try:
                    engine_compat = _fetch_vm_engine_compat(insp, vm["vm_guid"])
                except DataLoadError as exc:
                    section_errors["engine_compat"] = str(exc)
            else:
                try:
                    row = insp.fetch_one(
                        """
                        SELECT virtio_scsi_multi_queues_enabled
                        FROM vm_static
                        WHERE vm_guid = :vm_guid
                        """,
                        {"vm_guid": vm["vm_guid"]},
                    )
                    if row and row.get("virtio_scsi_multi_queues_enabled") is not None:
                        engine_compat = {
                            "release": "7.3",
                            "virtio_scsi": row["virtio_scsi_multi_queues_enabled"],
                        }
                except DataLoadError as exc:
                    if should_retry_narrow_sql(exc):
                        engine_compat = {}
                    else:
                        section_errors["engine_compat"] = str(exc)

            bios_code = vm["bios_type"]
            try:
                bios_key = int(bios_code) if bios_code is not None else None
            except (TypeError, ValueError):
                bios_key = None

            payload = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "header": {
                    "name": vm["vm_name"],
                    "id": vm["vm_guid"],
                    "description": vm["description"] or None,
                    "comment": vm["free_text_comment"] or None,
                    "os": _os_label(vm.get("os_name"), vm.get("os")),
                    "guest_os": guest_os_label(vm),
                    "template": vm["template_name"] or "—",
                    "bios": BIOS_TYPE_MAP.get(bios_key, f"Code {bios_code}")
                    if bios_code is not None
                    else "—",
                    "cluster": vm["cluster_name"] or "—",
                    "dc": vm["dc_name"] or "—",
                    "host": vm["host_name"] or "—",
                    "created": _fmt_date(vm["_create_date"]),
                    "updated": _fmt_date(vm["_update_date"]),
                },
                "metrics": {
                    "status": VM_STATUS_MAP.get(
                        vm["vm_status_code"], f"Code {vm['vm_status_code']}"
                    ),
                    "uptime": _uptime_label(
                        vm["vm_status_code"], vm["boot_time"], now_naive
                    ),
                    "cpu": _cpu_label(
                        vm["num_of_sockets"],
                        vm["cpu_per_socket"],
                        vm["threads_per_cpu"],
                    ),
                    "ram": _fmt_size_mb(vm["mem_size_mb"]),
                    "vm_ip": vm["vm_ip"] or "—",
                    "qemu_agent": _agent_label(vm.get("qemu_guest_agent_status")),
                    "ovirt_agent": _agent_label(vm.get("ovirt_guest_agent_status")),
                },
                "disks": disks,
                "layers": layers,
                "snapshots": snapshots,
                "networks": nics,
                "events": events,
                "engine_compat": engine_compat,
                "section_errors": section_errors,
                "nav_data": {
                    "host_id": vm["vds_id"],
                    "host_name": vm["host_name"],
                    "cluster_id": vm["cluster_id"],
                    "cluster_name": vm["cluster_name"],
                },
            }
            payload["report_text"] = format_vm_report(payload)
            return payload

    except DataLoadError as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

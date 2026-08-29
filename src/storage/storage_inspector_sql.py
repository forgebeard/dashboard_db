"""Диагностический отчёт по домену хранения (STORAGE-Inspector)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.constants import (
    HOST_STATUS_MAP,
    HOST_STATUS_UP,
    IMAGE_STATUS_ILLEGAL,
    IMAGE_STATUS_LOCKED,
    IMAGE_STATUS_MAP,
    IMAGE_STATUS_MERGING,
    SHARED_STATUS_MAP,
    STORAGE_DOMAIN_STATUS_ACTIVE,
    STORAGE_DOMAIN_STATUS_MAP,
    STORAGE_DOMAIN_TYPE_MAP,
    STORAGE_POOL_STATUS_MAP,
    STORAGE_SHARED_INACTIVE,
    STORAGE_SHARED_MIXED,
    STORAGE_TYPE_MAP,
    VM_STATUS_MAP,
)
from core.exceptions import DataLoadError
from core.inspector_base import InspectorBase
from core.report_text import BAR_DOUBLE, BAR_SINGLE
from core.report_text import _kv as _kv_core

EXTERNAL_STATUS_MAP = {0: "OK", 1: "Warning", 2: "Error"}
BLOCK_STORAGE_TYPES = frozenset({2, 3})  # FCP, iSCSI
GLANCE_STORAGE_TYPES = frozenset({8, 9, 10})  # Glance, Cinder, ManagedBlockStorage
BAD_IMAGE_STATUSES = (
    IMAGE_STATUS_ILLEGAL,
    IMAGE_STATUS_LOCKED,
    IMAGE_STATUS_MERGING,
)


def _kv(label: str, value: Any, width: int = 18) -> str:
    return _kv_core(label, value, width)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    return value in (True, 1, "1", "t", "true", "True")


def _fmt_gb(value: Any) -> str:
    num = _as_float(value)
    if num is None:
        return "—"
    return f"{int(round(num))} ГБ"


def _pct(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return round(part / whole * 100, 1)


def _code_label(code: Any, mapping: dict[int, str]) -> str:
    parsed = _as_int(code)
    if parsed is None:
        return "—"
    return mapping.get(parsed, f"Code {parsed}")


def _connection_kind(storage_type: Any) -> str:
    code = _as_int(storage_type)
    if code in BLOCK_STORAGE_TYPES:
        return "block"
    if code in GLANCE_STORAGE_TYPES:
        return "glance"
    if code is None:
        return "unknown"
    return "file"


def collect_storage_issues(payload: dict[str, Any]) -> list[str]:
    """Вердикт по кодам Engine, без Mixed=PROBLEM."""
    issues: list[str] = []
    shared_code = _as_int(payload.get("shared_code"))
    if shared_code in (STORAGE_SHARED_INACTIVE, STORAGE_SHARED_MIXED):
        issues.append(f"shared status: {_code_label(shared_code, SHARED_STATUS_MAP)}")

    for row in payload.get("attachments") or []:
        attach_code = _as_int(row.get("attach_code"))
        dc_name = row.get("dc_name") or "—"
        if attach_code is not None and attach_code != STORAGE_DOMAIN_STATUS_ACTIVE:
            issues.append(
                f"привязка {dc_name}: "
                f"{_code_label(attach_code, STORAGE_DOMAIN_STATUS_MAP)}"
            )
        spm_code = _as_int(row.get("spm_code"))
        if spm_code is not None and spm_code != HOST_STATUS_UP:
            issues.append(
                f"SPM {row.get('spm_host') or '—'}: "
                f"{_code_label(spm_code, HOST_STATUS_MAP)}"
            )

    space = payload.get("space") or {}
    free_pct = _as_float(space.get("free_pct"))
    warn_at = _as_float(space.get("warning_free_pct"))
    crit_at = _as_float(space.get("critical_free_pct"))
    if free_pct is not None and crit_at is not None and free_pct < crit_at:
        issues.append(f"свободно {free_pct}% < critical {int(crit_at)}%")
    elif free_pct is not None and warn_at is not None and free_pct < warn_at:
        issues.append(f"свободно {free_pct}% < warning {int(warn_at)}%")

    ext = _as_int(space.get("external_status"))
    if ext in (1, 2):
        issues.append(f"external status: {_code_label(ext, EXTERNAL_STATUS_MAP)}")

    for img in payload.get("images") or []:
        status = _as_int(img.get("status"))
        count = _as_int(img.get("count")) or 0
        if status in BAD_IMAGE_STATUSES and count > 0:
            issues.append(
                f"образы {_code_label(status, IMAGE_STATUS_MAP)}: {count}"
            )

    return issues


def format_storage_report(payload: dict[str, Any]) -> str:
    """Собирает текстовый отчёт по согласованному макету."""
    header = payload.get("header") or {}
    space = payload.get("space") or {}
    generated_at = payload.get("generated_at") or "—"
    flags: list[str] = []
    if header.get("is_master"):
        flags.append("Master")
    if header.get("is_he"):
        flags.append("Hosted Engine")
    if header.get("backup"):
        flags.append("backup")

    lines = [
        BAR_DOUBLE,
        f"  STORAGE-Inspector                                  {generated_at}",
        BAR_DOUBLE,
        "",
        "СВЕДЕНИЯ О ДОМЕНЕ",
        BAR_SINGLE,
        _kv("Имя", header.get("name")),
        _kv("UUID", header.get("id")),
        _kv("Тип домена", header.get("domain_type")),
        _kv("Протокол", header.get("storage_type")),
        _kv("Storage", header.get("storage_ref")),
        _kv("Формат", header.get("format")),
        _kv("Флаги", ", ".join(flags) if flags else "—"),
        "",
        "ПРИВЯЗКА",
        BAR_SINGLE,
        _kv("Shared", payload.get("shared_status")),
    ]
    attachments = payload.get("attachments") or []
    if not attachments:
        lines.append("  нет привязки к ДЦ")
    else:
        for row in attachments:
            spm = row.get("spm_host") or "—"
            spm_st = row.get("spm_status") or "—"
            lines.append(
                _kv("Дата-центр", f"{row.get('dc_name') or '—'}  [{row.get('dc_status') or '—'}]")
            )
            lines.append(_kv("Attach", row.get("attach_status")))
            lines.append(_kv("SPM", f"{spm}  [{spm_st}]"))

    used_pct = space.get("used_pct")
    free_pct = space.get("free_pct")
    used_bit = _fmt_gb(space.get("used"))
    if used_pct is not None:
        used_bit += f"  ({used_pct}%)"
    free_bit = _fmt_gb(space.get("free"))
    if free_pct is not None:
        free_bit += f"  ({free_pct}%)"
    warn_at = space.get("warning_free_pct")
    crit_at = space.get("critical_free_pct")
    thresh = "—"
    if warn_at is not None or crit_at is not None:
        thresh = f"warning {warn_at if warn_at is not None else '—'}% / critical {crit_at if crit_at is not None else '—'}% free"

    lines += [
        "",
        "МЕСТО",
        BAR_SINGLE,
        _kv("Занято", used_bit),
        _kv("Свободно", free_bit),
        _kv("Всего", _fmt_gb(space.get("total"))),
        _kv("Пороги", thresh),
        _kv("External", _code_label(space.get("external_status"), EXTERNAL_STATUS_MAP)),
    ]
    confirmed = space.get("confirmed_available")
    if confirmed not in (None, ""):
        lines.append(_kv("Confirmed", _fmt_gb(confirmed)))

    kind = payload.get("connection_kind") or "unknown"
    lines += ["", "ПОДКЛЮЧЕНИЕ", BAR_SINGLE]
    if kind == "block":
        luns = payload.get("luns") or []
        if not luns:
            lines.append("  нет LUN")
        else:
            for lun in luns:
                vendor = lun.get("vendor_id") or "—"
                product = lun.get("product_id") or ""
                size = lun.get("device_size")
                paths = lun.get("path_count")
                size_bit = f"{size} ГБ" if size not in (None, "") else "—"
                lines.append(
                    f"  LUN {lun.get('lun_id') or '—'}    {vendor} {product}".rstrip()
                )
                lines.append(
                    f"      размер {size_bit}    пути {paths if paths is not None else '—'}"
                )
        portals = payload.get("portals") or []
        if portals:
            lines.append("  Порталы:")
            for portal in portals:
                iqn = portal.get("iqn") or "—"
                conn = portal.get("connection") or "—"
                port = portal.get("port")
                port_bit = f":{port}" if port not in (None, "") else ""
                lines.append(f"    {conn}{port_bit}    {iqn}")
    elif kind == "file":
        conn = payload.get("file_connection") or {}
        if not conn.get("connection"):
            lines.append(_kv("Connection", header.get("storage_ref")))
        else:
            lines.append(_kv("Connection", conn.get("connection")))
            if conn.get("nfs_version") not in (None, ""):
                lines.append(_kv("NFS", conn.get("nfs_version")))
            if conn.get("mount_options"):
                lines.append(_kv("Mount", conn.get("mount_options")))
    elif kind == "glance":
        lines.append(_kv("Провайдер", header.get("storage_type")))
        lines.append(_kv("Storage", header.get("storage_ref")))
    else:
        lines.append(_kv("Storage", header.get("storage_ref")))

    lines += ["", "СОДЕРЖИМОЕ", BAR_SINGLE]
    images = payload.get("images") or []
    if not images:
        lines.append("  образы: нет")
    else:
        bits = [
            f"{_code_label(row.get('status'), IMAGE_STATUS_MAP)} {row.get('count')}"
            for row in images
        ]
        lines.append(f"  Образы: {', '.join(bits)}")
    vms = payload.get("vms") or []
    if not vms:
        lines.append("  ВМ: нет")
    else:
        for row in vms:
            entity = row.get("entity_type") or "—"
            st_label = _code_label(row.get("status"), VM_STATUS_MAP)
            lines.append(f"  {entity}: {st_label} × {row.get('count')}")
    bad = payload.get("bad_images") or []
    if bad:
        lines.append("  Проблемные:")
        for img in bad:
            vm_name = img.get("vm_name")
            alias = img.get("disk_alias") or "—"
            st_label = _code_label(img.get("imagestatus"), IMAGE_STATUS_MAP)
            extra = f"  ВМ {vm_name}" if vm_name else ""
            lines.append(f"    {st_label}  {alias}{extra}")

    issues = collect_storage_issues(payload)
    lines += ["", "ВЕРДИКТ", BAR_SINGLE]
    if issues:
        for item in issues:
            lines.append(f"  {item}")
    else:
        lines.append("  критичных проблем нет")

    lines += ["", BAR_DOUBLE, ""]
    return "\n".join(lines)


def get_storage_inspector_report(db_name: str, sd_id: str) -> dict:
    """Возвращает словарь с отчетом и навигационными данными."""
    sd_search = str(sd_id).strip()
    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)
            sd = insp.fetch_one(
                """
                SELECT
                    sds.id::text as sd_id,
                    sds.storage_name,
                    sds.storage_type,
                    sds.storage_domain_type,
                    sds.storage AS storage_ref,
                    sds.backup,
                    sds.storage_domain_format_type,
                    sds.warning_low_space_indicator,
                    sds.critical_space_action_blocker,
                    sdd.available_disk_size,
                    sdd.used_disk_size,
                    sdd.confirmed_available_disk_size,
                    sdd.external_status,
                    COALESCE(sdss.status, 0) as shared_status_code
                FROM storage_domain_static sds
                JOIN storage_domain_dynamic sdd ON sds.id = sdd.id
                LEFT JOIN storage_domain_shared_status sdss ON sds.id = sdss.storage_id
                WHERE sds.id::text = :sd_search
                LIMIT 1
                """,
                {"sd_search": sd_search},
            )
            if not sd:
                return {"error": "Хранилище не найдено.", "report_text": "", "nav_data": {}}

            params = {"sd_id": sd["sd_id"]}
            attachments = insp.fetch_all(
                """
                SELECT
                    sp.name as dc_name,
                    sp.id::text as pool_id,
                    spim.status as attach_status,
                    sp.status as dc_status,
                    vs.vds_name as spm_host,
                    vd.status as spm_code
                FROM storage_pool_iso_map spim
                JOIN storage_pool sp ON sp.id = spim.storage_pool_id
                LEFT JOIN vds_static vs ON vs.vds_id = sp.spm_vds_id
                LEFT JOIN vds_dynamic vd ON vd.vds_id = vs.vds_id
                WHERE spim.storage_id = CAST(:sd_id AS uuid)
                ORDER BY sp.name
                """,
                params,
            )
            he_row = insp.fetch_one(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM vm_static vm
                    JOIN vm_device d ON d.vm_id = vm.vm_guid
                    JOIN images i ON i.image_group_id = d.device_id
                    JOIN image_storage_domain_map m ON m.image_id = i.image_guid
                    WHERE vm.origin IN (5, 6)
                      AND i.active
                      AND m.storage_domain_id = CAST(:sd_id AS uuid)
                ) AS is_he
                """,
                params,
            )
            used = _as_float(sd["used_disk_size"]) or 0.0
            free = _as_float(sd["available_disk_size"]) or 0.0
            total = used + free
            kind = _connection_kind(sd["storage_type"])
            luns: list[dict[str, Any]] = []
            portals: list[dict[str, Any]] = []
            file_connection: dict[str, Any] = {}
            if kind == "block":
                luns = insp.fetch_all(
                    """
                    SELECT
                        l.lun_id,
                        l.vendor_id,
                        l.product_id,
                        l.serial,
                        l.device_size,
                        l.volume_group_id,
                        COUNT(m.storage_server_connection) AS path_count
                    FROM storage_domain_static sds
                    JOIN luns l ON l.volume_group_id = sds.storage
                    LEFT JOIN lun_storage_server_connection_map m
                           ON m.lun_id = l.lun_id
                    WHERE sds.id = CAST(:sd_id AS uuid)
                    GROUP BY l.lun_id, l.vendor_id, l.product_id, l.serial,
                             l.device_size, l.volume_group_id
                    """,
                    params,
                )
                portals = insp.fetch_all(
                    """
                    SELECT DISTINCT ssc.connection, ssc.iqn, ssc.port, ssc.portal
                    FROM storage_domain_static sds
                    JOIN luns l ON l.volume_group_id = sds.storage
                    JOIN lun_storage_server_connection_map m ON m.lun_id = l.lun_id
                    JOIN storage_server_connections ssc
                         ON ssc.id = m.storage_server_connection
                    WHERE sds.id = CAST(:sd_id AS uuid)
                    ORDER BY ssc.connection
                    """,
                    params,
                )
            elif kind == "file":
                row = insp.fetch_one(
                    """
                    SELECT ssc.connection, ssc.nfs_version, ssc.mount_options, ssc.iqn
                    FROM storage_domain_static sds
                    LEFT JOIN storage_server_connections ssc
                           ON ssc.id::text = sds.storage
                    WHERE sds.id = CAST(:sd_id AS uuid)
                    LIMIT 1
                    """,
                    params,
                )
                file_connection = row or {}

            images = insp.fetch_all(
                """
                SELECT i.imagestatus as status, COUNT(*) as count
                FROM images i
                JOIN image_storage_domain_map m ON m.image_id = i.image_guid
                WHERE m.storage_domain_id = CAST(:sd_id AS uuid)
                GROUP BY i.imagestatus
                ORDER BY i.imagestatus
                """,
                params,
            )
            vms = insp.fetch_all(
                """
                SELECT vs.entity_type, vdyn.status, COUNT(DISTINCT vs.vm_guid) as count
                FROM image_storage_domain_map m
                JOIN images i ON i.image_guid = m.image_id
                JOIN vm_device d ON d.device_id = i.image_group_id
                JOIN vm_static vs ON vs.vm_guid = d.vm_id
                LEFT JOIN vm_dynamic vdyn ON vdyn.vm_guid = vs.vm_guid
                WHERE m.storage_domain_id = CAST(:sd_id AS uuid)
                GROUP BY vs.entity_type, vdyn.status
                ORDER BY vs.entity_type, vdyn.status
                """,
                params,
            )
            bad_images: list[dict[str, Any]] = []
            if any(
                _as_int(row.get("status")) in BAD_IMAGE_STATUSES
                and (_as_int(row.get("count")) or 0) > 0
                for row in images
            ):
                bad_images = insp.fetch_all(
                    """
                    SELECT
                        bd.disk_alias,
                        i.imagestatus,
                        vs.vm_name
                    FROM images i
                    JOIN image_storage_domain_map m ON m.image_id = i.image_guid
                    JOIN base_disks bd ON i.image_group_id = bd.disk_id
                    LEFT JOIN vm_device d ON d.device_id = bd.disk_id
                    LEFT JOIN vm_static vs ON vs.vm_guid = d.vm_id
                    WHERE m.storage_domain_id = CAST(:sd_id AS uuid)
                      AND i.imagestatus IN (:st_locked, :st_illegal, :st_merging)
                    ORDER BY i.imagestatus, bd.disk_alias
                    LIMIT 15
                    """,
                    {
                        **params,
                        "st_locked": IMAGE_STATUS_LOCKED,
                        "st_illegal": IMAGE_STATUS_ILLEGAL,
                        "st_merging": IMAGE_STATUS_MERGING,
                    },
                )

            domain_type_code = _as_int(sd["storage_domain_type"])
            payload: dict[str, Any] = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "header": {
                    "name": sd["storage_name"],
                    "id": sd["sd_id"],
                    "domain_type": _code_label(
                        domain_type_code, STORAGE_DOMAIN_TYPE_MAP
                    ),
                    "storage_type": _code_label(sd["storage_type"], STORAGE_TYPE_MAP),
                    "storage_ref": sd["storage_ref"],
                    "format": sd["storage_domain_format_type"],
                    "is_master": domain_type_code == 0,
                    "is_he": _as_bool(he_row.get("is_he") if he_row else False),
                    "backup": _as_bool(sd["backup"]),
                },
                "shared_code": sd["shared_status_code"],
                "shared_status": _code_label(
                    sd["shared_status_code"], SHARED_STATUS_MAP
                ),
                "attachments": [
                    {
                        "dc_name": row.get("dc_name"),
                        "pool_id": row.get("pool_id"),
                        "attach_code": row.get("attach_status"),
                        "attach_status": _code_label(
                            row.get("attach_status"), STORAGE_DOMAIN_STATUS_MAP
                        ),
                        "dc_status": _code_label(
                            row.get("dc_status"), STORAGE_POOL_STATUS_MAP
                        ),
                        "spm_host": row.get("spm_host"),
                        "spm_code": row.get("spm_code"),
                        "spm_status": _code_label(row.get("spm_code"), HOST_STATUS_MAP),
                    }
                    for row in attachments
                ],
                "space": {
                    "used": used,
                    "free": free,
                    "total": total,
                    "used_pct": _pct(used, total),
                    "free_pct": _pct(free, total),
                    "warning_free_pct": _as_float(sd["warning_low_space_indicator"]),
                    "critical_free_pct": _as_float(
                        sd["critical_space_action_blocker"]
                    ),
                    "external_status": sd["external_status"],
                    "confirmed_available": sd["confirmed_available_disk_size"],
                },
                "connection_kind": kind,
                "luns": luns,
                "portals": portals,
                "file_connection": file_connection,
                "images": images,
                "vms": vms,
                "bad_images": bad_images,
                "nav_data": {
                    "pool_id": attachments[0]["pool_id"] if attachments else None,
                    "dc_name": attachments[0]["dc_name"] if attachments else None,
                    "spm_host_name": attachments[0]["spm_host"] if attachments else None,
                },
            }
            payload["report_text"] = format_storage_report(payload)
            return payload
    except DataLoadError as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

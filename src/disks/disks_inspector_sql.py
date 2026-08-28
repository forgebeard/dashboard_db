"""Диагностический отчёт по слою диска. Сбор отдельно от вёрстки — как VM-Inspector."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.constants import (
    IMAGE_STATUS_MAP,
    VM_STATUS_MAP,
    action_type_label,
    async_task_status_label,
    mapped_code_label,
)
from core.inspector_base import InspectorBase
from vms.vm_inspector_sql import (
    BAR_DOUBLE,
    BAR_SINGLE,
    _fmt_size_bytes,
    _fmt_ts,
    _id_text,
    _kv,
    _kv_at,
    _norm_id,
    _volume_bit,
    _yes_no,
    order_layers_by_parent,
)


def _image_status_label(code: Any) -> str:
    return mapped_code_label(code, IMAGE_STATUS_MAP)


def _vm_status_label(code: Any) -> str:
    return mapped_code_label(code, VM_STATUS_MAP)


def _content_type_label(code: Any) -> str:
    if code in (None, ""):
        return "—"
    return mapped_code_label(code, {})


def _storage_line(names: list[str]) -> str:
    cleaned = [name for name in names if name not in (None, "")]
    return ", ".join(cleaned) if cleaned else "—"


def format_disk_report(payload: dict[str, Any]) -> str:
    """Текстовый отчёт: выбранный слой, диск, привязки, цепочка, задачи."""
    selected = payload.get("selected") or {}
    attachments = payload.get("attachments") or []
    layers = payload.get("layers") or []
    tasks = payload.get("tasks") or []
    section_errors = payload.get("section_errors") or {}
    generated_at = payload.get("generated_at") or "—"
    selected_guid = _norm_id(selected.get("image_guid"))

    lines = [
        BAR_DOUBLE,
        f"  DISK-Inspector                                         {generated_at}",
        BAR_DOUBLE,
        "",
        "ВЫБРАННЫЙ СЛОЙ",
        BAR_SINGLE,
    ]

    if not selected:
        lines.append("  слой не найден")
    else:
        lines.append(_kv("image_guid", selected.get("image_guid")))
        lines.append(_kv("статус", _image_status_label(selected.get("imagestatus"))))
        lines.append(_kv("active", _yes_no(selected.get("active"))))
        lines.append(_kv("parentid", _id_text(selected.get("parentid"))))
        lines.append(_kv("вирт. размер", _fmt_size_bytes(selected.get("virt_size"))))
        lines.append(_kv("факт. размер", _fmt_size_bytes(selected.get("actual_size"))))
        lines.append(_kv("хранилище", selected.get("storage_name") or "—"))
        snap_id = selected.get("snapshot_id")
        snap_line = _id_text(snap_id) or "—"
        snap_name = selected.get("snap_name")
        if snap_name not in (None, ""):
            snap_line = f"{snap_line}    {snap_name}"
        lines.append(_kv("снапшот", snap_line))
        lines.append(_kv("создан", _fmt_ts(selected.get("creation_date"))))

    lines += ["", "ДИСК", BAR_SINGLE]
    if not selected:
        lines.append("  диск не найден")
    else:
        lines.append(_kv("disk_id", selected.get("disk_id")))
        lines.append(_kv("имя", selected.get("disk_alias") or "—"))
        lines.append(_kv("shareable", _yes_no(selected.get("shareable"))))
        lines.append(_kv("wipe", _yes_no(selected.get("wipe_after_delete"))))
        lines.append(_kv("тип", _volume_bit(selected) or "—"))
        lines.append(_kv("content_type", _content_type_label(selected.get("disk_content_type"))))

    lines += ["", "ПРИВЯЗКИ", BAR_SINGLE]
    if section_errors.get("attachments"):
        lines.append(f"  ошибка чтения ({section_errors['attachments']})")
    elif not attachments:
        lines.append("  не привязан")
    else:
        for row in attachments:
            lines.append(_kv_at("    ", "ВМ", row.get("vm_name") or "—"))
            lines.append(_kv_at("    ", "UUID", row.get("vm_id")))
            lines.append(_kv_at("    ", "статус", _vm_status_label(row.get("vm_status_code"))))
            lines.append(_kv_at("    ", "подключён", _yes_no(row.get("is_plugged"))))
            lines.append(_kv_at("    ", "boot", _yes_no(row.get("is_boot"))))
            lines.append(_kv_at("    ", "шина", row.get("disk_interface") or "—"))
            lines.append("")

    lines += ["", "СЛОИ", BAR_SINGLE]
    if section_errors.get("layers"):
        lines.append(f"  ошибка чтения ({section_errors['layers']})")
    elif not layers:
        lines.append("  нет слоёв")
    else:
        for layer in order_layers_by_parent(layers):
            guid = layer.get("image_guid")
            marker = _norm_id(guid) == selected_guid and bool(selected_guid)
            label = str(guid) if guid not in (None, "") else "—"
            if marker:
                label = f"{label}     ← выбран"
            lines.append(_kv_at("    ", "image_guid", label))
            lines.append(_kv_at("    ", "parentid", _id_text(layer.get("parentid"))))
            lines.append(_kv_at("    ", "статус", _image_status_label(layer.get("imagestatus"))))
            if layer.get("active"):
                lines.append(_kv_at("    ", "состояние", "active"))
            lines.append(_kv_at("    ", "тип", _volume_bit(layer) or "—"))
            lines.append(
                _kv_at(
                    "    ",
                    "размер",
                    _fmt_size_bytes(layer.get("actual_size") or layer.get("size")),
                )
            )
            snap = _id_text(layer.get("vm_snapshot_id")) or "—"
            lines.append(_kv_at("    ", "снапшот", snap))
            lines.append("")

    lines += ["", "ЗАДАЧИ", BAR_SINGLE]
    if section_errors.get("tasks"):
        lines.append(f"  ошибка чтения ({section_errors['tasks']})")
    elif not tasks:
        lines.append("  нет")
    else:
        for task in tasks:
            lines.append(_kv_at("    ", "задача", action_type_label(task.get("action_type"))))
            lines.append(
                _kv_at("    ", "статус", async_task_status_label(task.get("status")))
            )
            lines.append(_kv_at("    ", "старт", _fmt_ts(task.get("started_at"))))
            tid = _id_text(task.get("task_id"))
            if tid:
                lines.append(_kv_at("    ", "task_id", tid))
            lines.append("")

    lines.append(BAR_DOUBLE)
    return "\n".join(lines)


def get_disk_inspector_report(db_name: str, image_guid: str) -> dict:
    """Отчёт по выбранному слою диска (image_guid)."""
    img_search = str(image_guid).strip()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)
            selected = insp.fetch_one(
                """
                SELECT
                    i.image_guid::text,
                    i.image_group_id::text AS disk_id,
                    bd.disk_alias,
                    bd.shareable,
                    bd.wipe_after_delete,
                    bd.disk_content_type,
                    i.imagestatus,
                    i.size AS virt_size,
                    did.actual_size,
                    i.active,
                    i.creation_date,
                    i.parentid::text,
                    i.volume_type,
                    i.volume_format,
                    i.vm_snapshot_id::text AS snapshot_id,
                    vs.description AS snap_name
                FROM images i
                JOIN base_disks bd ON i.image_group_id = bd.disk_id
                LEFT JOIN disk_image_dynamic did ON i.image_guid = did.image_id
                LEFT JOIN snapshots vs ON i.vm_snapshot_id = vs.snapshot_id
                WHERE i.image_guid::text = :image_guid
                LIMIT 1
                """,
                {"image_guid": img_search},
            )
            if not selected:
                return {"error": "Образ не найден.", "report_text": "", "nav_data": {}}

            section_errors: dict[str, str] = {}
            disk_id = selected["disk_id"]
            image_id = selected["image_guid"]

            try:
                storage_rows = insp.fetch_all(
                    """
                    SELECT sd.storage_name
                    FROM image_storage_domain_map m
                    JOIN storage_domain_static sd ON sd.id = m.storage_domain_id
                    WHERE m.image_id::text = :image_guid
                    ORDER BY sd.storage_name
                    """,
                    {"image_guid": image_id},
                )
                selected["storage_name"] = _storage_line(
                    [row.get("storage_name") for row in storage_rows]
                )
            except Exception as exc:
                section_errors["storage"] = str(exc)
                selected["storage_name"] = "—"

            attachments: list[dict[str, Any]] = []
            try:
                attachments = insp.fetch_all(
                    """
                    SELECT
                        vm.vm_guid::text AS vm_id,
                        vm.vm_name,
                        vdyn.status AS vm_status_code,
                        vd.is_plugged,
                        dve.is_boot,
                        dve.disk_interface
                    FROM vm_device vd
                    JOIN vm_static vm ON vd.vm_id = vm.vm_guid
                    LEFT JOIN vm_dynamic vdyn ON vm.vm_guid = vdyn.vm_guid
                    LEFT JOIN disk_vm_element dve
                           ON dve.disk_id = vd.device_id AND dve.vm_id = vd.vm_id
                    WHERE vd.device_id = CAST(:disk_id AS uuid)
                      AND vd.type = 'disk'
                    ORDER BY vm.vm_name
                    """,
                    {"disk_id": disk_id},
                )
            except Exception as exc:
                section_errors["attachments"] = str(exc)

            layers: list[dict[str, Any]] = []
            try:
                layers = insp.fetch_all(
                    """
                    SELECT
                        bd.disk_alias,
                        i.image_guid::text,
                        i.parentid::text,
                        i.active,
                        i.imagestatus,
                        i.volume_type,
                        i.volume_format,
                        i.vm_snapshot_id::text,
                        i.size,
                        did.actual_size,
                        string_agg(DISTINCT sd.storage_name, ', ') AS storage_name
                    FROM images i
                    JOIN base_disks bd ON i.image_group_id = bd.disk_id
                    LEFT JOIN disk_image_dynamic did ON did.image_id = i.image_guid
                    LEFT JOIN image_storage_domain_map m ON m.image_id = i.image_guid
                    LEFT JOIN storage_domain_static sd ON sd.id = m.storage_domain_id
                    WHERE i.image_group_id = CAST(:disk_id AS uuid)
                    GROUP BY
                        bd.disk_alias,
                        i.image_guid,
                        i.parentid,
                        i.active,
                        i.imagestatus,
                        i.volume_type,
                        i.volume_format,
                        i.vm_snapshot_id,
                        i.size,
                        did.actual_size
                    """,
                    {"disk_id": disk_id},
                )
            except Exception as exc:
                section_errors["layers"] = str(exc)

            tasks: list[dict[str, Any]] = []
            try:
                tasks = insp.fetch_all(
                    """
                    SELECT
                        at.task_id::text,
                        at.action_type,
                        at.status,
                        at.started_at
                    FROM async_tasks at
                    JOIN async_tasks_entities ate ON at.task_id = ate.async_task_id
                    WHERE ate.entity_id::text IN (:image_guid, :disk_id)
                    ORDER BY at.started_at DESC
                    LIMIT 10
                    """,
                    {"image_guid": image_id, "disk_id": disk_id},
                )
            except Exception as exc:
                section_errors["tasks"] = str(exc)

            first = attachments[0] if attachments else {}
            payload = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "selected": selected,
                "attachments": attachments,
                "layers": layers,
                "tasks": tasks,
                "section_errors": section_errors,
                "nav_data": {
                    "disk_id": disk_id,
                    "image_guid": image_id,
                    "vm_id": first.get("vm_id"),
                    "vm_name": first.get("vm_name"),
                },
            }
            payload["report_text"] = format_disk_report(payload)
            return payload

    except Exception as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

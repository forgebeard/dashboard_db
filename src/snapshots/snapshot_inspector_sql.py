"""Диагностический отчёт по снапшоту. Сбор отдельно от вёрстки — как VM-Inspector."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.constants import mapped_code_label, IMAGE_STATUS_MAP
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
    snapshot_type_label,
)

_SNAPSHOT_EXTRA_COLS = (
    "s.vm_configuration_broken",
    "s.changed_fields",
    "s.app_list",
)


def _image_status_label(code: Any) -> str:
    return mapped_code_label(code, IMAGE_STATUS_MAP)


def _layers_for_snapshot(
    layers: list[dict[str, Any]], snapshot_id: Any
) -> list[dict[str, Any]]:
    want = _norm_id(snapshot_id)
    if not want:
        return []
    return [row for row in layers if _norm_id(row.get("vm_snapshot_id")) == want]


def _layer_guids(rows: list[dict[str, Any]]) -> list[str]:
    guids: list[str] = []
    for row in rows:
        guid = row.get("image_guid")
        if guid not in (None, ""):
            guids.append(str(guid))
    return guids


def _layer_size(layer: dict[str, Any]) -> Any:
    actual = layer.get("actual_size")
    if actual not in (None, ""):
        return actual
    return layer.get("size")


def _append_layer_card(
    lines: list[str],
    layer: dict[str, Any],
    *,
    selected_snap: str,
    with_storage: bool,
) -> None:
    lines.append(_kv_at("    ", "диск", layer.get("disk_alias") or "—"))
    lines.append(_kv_at("    ", "image_guid", layer.get("image_guid")))
    if layer.get("active"):
        lines.append(_kv_at("    ", "состояние", "active"))
    lines.append(_kv_at("    ", "parentid", _id_text(layer.get("parentid"))))
    lines.append(_kv_at("    ", "статус", _image_status_label(layer.get("imagestatus"))))
    if with_storage:
        lines.append(_kv_at("    ", "тип", _volume_bit(layer) or "—"))
        lines.append(_kv_at("    ", "размер", _fmt_size_bytes(_layer_size(layer))))
        lines.append(_kv_at("    ", "хранилище", layer.get("storage_name") or "—"))
    else:
        snap_id = layer.get("vm_snapshot_id")
        label = str(snap_id) if snap_id not in (None, "") else "—"
        if _norm_id(snap_id) == _norm_id(selected_snap) and _norm_id(selected_snap):
            label = f"{label}     ← выбран"
        lines.append(_kv_at("    ", "снапшот", label))
    lines.append("")


def _append_guid_list(lines: list[str], guids: list[str]) -> None:
    if not guids:
        lines.append(_kv_at("    ", "слои", "—"))
    elif len(guids) == 1:
        lines.append(_kv_at("    ", "слои", guids[0]))
    else:
        lines.append("    слои:")
        for guid in guids:
            lines.append(f"      {guid}")


def _memory_line(disk_id: Any, alias: Any) -> str | None:
    ident = _id_text(disk_id)
    if not ident:
        return None
    name = alias if alias not in (None, "") else "—"
    return f"{ident}    {name}"


def format_snapshot_report(payload: dict[str, Any]) -> str:
    """Текстовый отчёт: выбранный снимок, слои, цепочка ВМ, чекпоинты."""
    header = payload.get("header") or {}
    selected = payload.get("selected") or {}
    snapshots = payload.get("snapshots") or []
    layers = payload.get("layers") or []
    checkpoints = payload.get("checkpoints") or []
    section_errors = payload.get("section_errors") or {}
    generated_at = payload.get("generated_at") or "—"
    selected_id = selected.get("snapshot_id")
    selected_layers = _layers_for_snapshot(layers, selected_id)

    lines = [
        BAR_DOUBLE,
        f"  Snapshot-Inspector                                     {generated_at}",
        BAR_DOUBLE,
        "",
        "ВМ",
        BAR_SINGLE,
        _kv("имя", header.get("name")),
        _kv("UUID", header.get("id")),
        _kv("кластер", header.get("cluster")),
        _kv("дата-центр", header.get("dc")),
        "",
        "ВЫБРАННЫЙ СНАПШОТ",
        BAR_SINGLE,
    ]

    if not selected:
        lines.append("  снапшот не найден")
    else:
        lines.append(_kv_at("    ", "snapshot_id", selected.get("snapshot_id")))
        lines.append(
            _kv_at("    ", "тип", snapshot_type_label(selected.get("snapshot_type")))
        )
        lines.append(_kv_at("    ", "статус", selected.get("status") or "—"))
        lines.append(_kv_at("    ", "дата", _fmt_ts(selected.get("creation_date"))))
        lines.append(_kv_at("    ", "имя", selected.get("description") or "—"))
        if selected.get("vm_configuration_broken") is not None:
            lines.append(
                _kv_at(
                    "    ",
                    "broken",
                    _yes_no(selected.get("vm_configuration_broken")),
                )
            )
        app_list = selected.get("app_list")
        if app_list not in (None, ""):
            lines.append(_kv_at("    ", "app_list", app_list))
        changed = selected.get("changed_fields")
        if changed not in (None, ""):
            lines.append(_kv_at("    ", "changed_fields", changed))
        dump_line = _memory_line(
            selected.get("memory_dump_disk_id"), selected.get("memory_dump_alias")
        )
        meta_line = _memory_line(
            selected.get("memory_metadata_disk_id"),
            selected.get("memory_metadata_alias"),
        )
        if dump_line:
            lines.append(_kv_at("    ", "память dump", dump_line))
        if meta_line:
            lines.append(_kv_at("    ", "память meta", meta_line))
        _append_guid_list(lines, _layer_guids(selected_layers))

    lines += ["", "СЛОИ ЭТОГО СНАПШОТА", BAR_SINGLE]
    if section_errors.get("layers"):
        lines.append(f"  ошибка чтения ({section_errors['layers']})")
    elif not selected_layers:
        lines.append("  нет слоёв")
    else:
        for layer in order_layers_by_parent(selected_layers):
            _append_layer_card(
                lines, layer, selected_snap=str(selected_id or ""), with_storage=True
            )

    lines += ["", "ЦЕПОЧКА ВМ", BAR_SINGLE]
    if section_errors.get("snapshots"):
        lines.append(f"  ошибка чтения ({section_errors['snapshots']})")
    elif not snapshots:
        lines.append("  нет снапшотов")
    else:
        want = _norm_id(selected_id)
        for snap in snapshots:
            marker = _norm_id(snap.get("snapshot_id")) == want
            prefix = "  ► " if marker else "    "
            sid = snap.get("snapshot_id") or "—"
            lines.append(f"{prefix}{('snapshot_id:'):<16}{sid}")
            lines.append(
                _kv_at("    ", "тип", snapshot_type_label(snap.get("snapshot_type")))
            )
            lines.append(_kv_at("    ", "дата", _fmt_ts(snap.get("creation_date"))))
            lines.append(_kv_at("    ", "имя", snap.get("description") or "—"))
            linked = _layers_for_snapshot(layers, snap.get("snapshot_id"))
            count = snap.get("layer_count")
            if count is None:
                count = len(_layer_guids(linked))
            lines.append(_kv_at("    ", "слои", count))
            lines.append("")

    lines += ["", "СЛОИ ВМ (по дискам, корень → лист)", BAR_SINGLE]
    if section_errors.get("layers"):
        lines.append(f"  ошибка чтения ({section_errors['layers']})")
    elif not layers:
        lines.append("  нет слоёв")
    else:
        for layer in order_layers_by_parent(layers):
            _append_layer_card(
                lines, layer, selected_snap=str(selected_id or ""), with_storage=False
            )

    lines += ["", "ЧЕКПОИНТЫ", BAR_SINGLE]
    if section_errors.get("checkpoints"):
        lines.append(f"  ошибка чтения ({section_errors['checkpoints']})")
    elif not checkpoints:
        lines.append("  нет чекпоинтов")
    else:
        for cp in checkpoints:
            lines.append(_kv_at("    ", "checkpoint_id", cp.get("checkpoint_id")))
            parent = cp.get("parent_id")
            lines.append(
                _kv_at("    ", "parent_id", _id_text(parent) if parent else "—")
            )
            lines.append(_kv_at("    ", "дата", _fmt_ts(cp.get("_create_date"))))
            lines.append(_kv_at("    ", "state", cp.get("state") or "—"))
            lines.append(_kv_at("    ", "описание", cp.get("description") or "—"))
            lines.append("")

    lines += ["", BAR_DOUBLE, ""]
    return "\n".join(lines)


def _fetch_snapshots(insp: InspectorBase, vm_guid: Any) -> list[dict[str, Any]]:
    params = {"vm_guid": vm_guid}
    base_select = """
        SELECT
            s.snapshot_id::text,
            s.snapshot_type,
            s.status,
            s.description,
            s.creation_date,
            s.memory_dump_disk_id::text,
            s.memory_metadata_disk_id::text,
            dump.disk_alias AS memory_dump_alias,
            meta.disk_alias AS memory_metadata_alias
            {extra}
        FROM snapshots s
        LEFT JOIN base_disks dump ON dump.disk_id = s.memory_dump_disk_id
        LEFT JOIN base_disks meta ON meta.disk_id = s.memory_metadata_disk_id
        WHERE s.vm_id = :vm_guid
        ORDER BY s.creation_date
    """
    extra_sql = ",\n            " + ",\n            ".join(_SNAPSHOT_EXTRA_COLS)
    try:
        return insp.fetch_all(base_select.format(extra=extra_sql), params)
    except Exception:
        return insp.fetch_all(base_select.format(extra=""), params)


def get_snapshot_inspector_report(
    db_name: str, vm_id: str, snapshot_id: str
) -> dict:
    """Отчёт по выбранному снапшоту ВМ."""
    vm_search = str(vm_id).strip().lower()
    snap_search = _norm_id(snapshot_id)

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)
            vm = insp.fetch_one(
                """
                SELECT
                    v.vm_guid, v.vm_name,
                    c.name AS cluster_name, dc.name AS dc_name
                FROM vm_static v
                LEFT JOIN cluster c ON v.cluster_id = c.cluster_id
                LEFT JOIN storage_pool dc ON c.storage_pool_id = dc.id
                WHERE v.vm_guid::text = :vm_search
                LIMIT 1
                """,
                {"vm_search": vm_search},
            )
            if not vm:
                return {"error": "ВМ не найдена.", "report_text": "", "nav_data": {}}

            section_errors: dict[str, str] = {}
            params = {"vm_guid": vm["vm_guid"]}
            snapshots: list[dict[str, Any]] = []
            layers: list[dict[str, Any]] = []
            checkpoints: list[dict[str, Any]] = []

            try:
                snapshots = _fetch_snapshots(insp, vm["vm_guid"])
            except Exception as exc:
                section_errors["snapshots"] = str(exc)

            selected = next(
                (
                    row
                    for row in snapshots
                    if _norm_id(row.get("snapshot_id")) == snap_search
                ),
                None,
            )
            if not selected:
                return {
                    "error": "Снапшот не найден.",
                    "report_text": "",
                    "nav_data": {},
                }

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
                        sd.storage_name
                    FROM vm_device vd
                    JOIN base_disks bd ON bd.disk_id = vd.device_id
                    JOIN images i ON i.image_group_id = bd.disk_id
                    LEFT JOIN disk_image_dynamic did ON did.image_id = i.image_guid
                    LEFT JOIN image_storage_domain_map m ON m.image_id = i.image_guid
                    LEFT JOIN storage_domain_static sd ON sd.id = m.storage_domain_id
                    WHERE vd.vm_id = :vm_guid AND vd.type = 'disk'
                    ORDER BY bd.disk_alias, i.creation_date
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["layers"] = str(exc)

            try:
                checkpoints = insp.fetch_all(
                    """
                    SELECT
                        cp.checkpoint_id::text,
                        cp.parent_id::text,
                        cp._create_date,
                        cp.state,
                        cp.description
                    FROM vm_checkpoints cp
                    WHERE cp.vm_id = :vm_guid
                    ORDER BY cp._create_date
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["checkpoints"] = str(exc)

            payload = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "header": {
                    "name": vm["vm_name"],
                    "id": vm["vm_guid"],
                    "cluster": vm["cluster_name"] or "—",
                    "dc": vm["dc_name"] or "—",
                },
                "selected": selected,
                "snapshots": snapshots,
                "layers": layers,
                "checkpoints": checkpoints,
                "section_errors": section_errors,
                "nav_data": {
                    "vm_id": vm_search,
                    "vm_name": vm["vm_name"],
                    "snapshot_id": selected.get("snapshot_id"),
                },
            }
            payload["report_text"] = format_snapshot_report(payload)
            return payload

    except Exception as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

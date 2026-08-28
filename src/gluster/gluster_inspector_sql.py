"""Диагностический отчёт по тому Gluster. Сбор отдельно от вёрстки."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.inspector_base import InspectorBase
from vms.vm_inspector_sql import (
    BAR_DOUBLE,
    BAR_SINGLE,
    _fmt_size_bytes,
    _fmt_ts,
    _kv,
    _kv_at,
    _yes_no,
)


def _dash(value: Any) -> str:
    if value in (None, ""):
        return "—"
    return str(value)


def _usage_pct(used: Any, total: Any) -> str:
    if used in (None, "") or total in (None, ""):
        return "—"
    try:
        whole = float(total)
        part = float(used)
    except (TypeError, ValueError):
        return "—"
    if whole <= 0:
        return "—"
    return f"{round(part / whole * 100, 1)}%"


def format_gluster_report(payload: dict[str, Any]) -> str:
    """Текстовый отчёт: том, кирпичи, опции, geo, снапшоты."""
    header = payload.get("header") or {}
    bricks = payload.get("bricks") or []
    options = payload.get("options") or []
    georep = payload.get("georep") or []
    snapshots = payload.get("snapshots") or []
    section_errors = payload.get("section_errors") or {}
    generated_at = payload.get("generated_at") or "—"

    used = header.get("used_space")
    total = header.get("total_space")
    pct = _usage_pct(used, total)

    lines = [
        BAR_DOUBLE,
        f"  Gluster-Inspector                                      {generated_at}",
        BAR_DOUBLE,
        "",
        "ТОМ",
        BAR_SINGLE,
    ]
    if not header:
        lines.append("  том не найден")
    else:
        lines.append(_kv("имя", header.get("vol_name") or "—"))
        lines.append(_kv("UUID", header.get("id")))
        lines.append(_kv("кластер", header.get("cluster_name") or "—"))
        lines.append(_kv("тип", _dash(header.get("vol_type"))))
        lines.append(_kv("статус", _dash(header.get("status"))))
        lines.append(_kv("replica", _dash(header.get("replica_count"))))
        lines.append(_kv("disperse", _dash(header.get("disperse_count"))))
        lines.append(_kv("stripe", _dash(header.get("stripe_count"))))
        lines.append(_kv("снапшоты", _dash(header.get("snapshot_count"))))
        lines.append(_kv("занято", _fmt_size_bytes(used)))
        lines.append(_kv("всего", _fmt_size_bytes(total)))
        lines.append(_kv("заполнено", pct))

    lines += ["", "КИРПИЧИ", BAR_SINGLE]
    if section_errors.get("bricks"):
        lines.append(f"  ошибка чтения ({section_errors['bricks']})")
    elif not bricks:
        lines.append("  нет кирпичей")
    else:
        for row in bricks:
            brick_used = row.get("brick_used")
            brick_total = row.get("brick_total")
            lines.append(_kv_at("    ", "хост", row.get("vds_name") or "—"))
            lines.append(_kv_at("    ", "UUID", row.get("id")))
            lines.append(_kv_at("    ", "путь", row.get("brick_dir") or "—"))
            lines.append(_kv_at("    ", "адрес", row.get("interface_address") or "—"))
            lines.append(_kv_at("    ", "статус", _dash(row.get("brick_status"))))
            lines.append(_kv_at("    ", "arbiter", _yes_no(row.get("is_arbiter"))))
            lines.append(_kv_at("    ", "занято", _fmt_size_bytes(brick_used)))
            lines.append(_kv_at("    ", "заполнено", _usage_pct(brick_used, brick_total)))
            lines.append("")

    lines += ["", "ОПЦИИ", BAR_SINGLE]
    if section_errors.get("options"):
        lines.append(f"  ошибка чтения ({section_errors['options']})")
    elif not options:
        lines.append("  нет опций")
    else:
        for row in options:
            key = row.get("option_key") or "—"
            val = row.get("option_val")
            val_text = "—" if val in (None, "") else str(val)
            lines.append(_kv_at("    ", "опция", f"{key} = {val_text}"))

    lines += ["", "GEO", BAR_SINGLE]
    if section_errors.get("georep"):
        lines.append(f"  ошибка чтения ({section_errors['georep']})")
    elif not georep:
        lines.append("  нет geo")
    else:
        for row in georep:
            slave = f"{_dash(row.get('slave_host_name'))}/{_dash(row.get('slave_volume_name'))}"
            lines.append(_kv_at("    ", "slave", slave))
            lines.append(_kv_at("    ", "статус", _dash(row.get("geo_status"))))
            lines.append(_kv_at("    ", "checkpoint", _dash(row.get("checkpoint_status"))))
            pending = row.get("data_pending")
            lines.append(
                _kv_at("    ", "pending", "—" if pending in (None, "") else pending)
            )
            lines.append(_kv_at("    ", "last_sync", _fmt_ts(row.get("last_synced_at"))))
            lines.append("")

    lines += ["", "СНАПШОТЫ", BAR_SINGLE]
    if section_errors.get("snapshots"):
        lines.append(f"  ошибка чтения ({section_errors['snapshots']})")
    elif not snapshots:
        lines.append("  нет снапшотов")
    else:
        for row in snapshots:
            lines.append(_kv_at("    ", "имя", row.get("snapshot_name") or "—"))
            lines.append(_kv_at("    ", "статус", _dash(row.get("status"))))
            lines.append(_kv_at("    ", "_create_date", _fmt_ts(row.get("_create_date"))))
            lines.append(_kv_at("    ", "описание", row.get("description") or "—"))
            lines.append("")

    lines.append(BAR_DOUBLE)
    return "\n".join(lines)


def get_gluster_volume_report(db_name: str, volume_id: str) -> dict:
    """Отчёт по тому Gluster."""
    vid_search = str(volume_id).strip().lower()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)
            header = insp.fetch_one(
                """
                SELECT
                    v.id::text,
                    v.vol_name,
                    v.cluster_name,
                    v.vol_type,
                    v.status,
                    v.replica_count,
                    v.disperse_count,
                    v.stripe_count,
                    v.snapshot_count,
                    vd.total_space,
                    vd.used_space,
                    vd.free_space
                FROM gluster_volumes_view v
                LEFT JOIN gluster_volume_details vd ON v.id::text = vd.volume_id::text
                WHERE LOWER(v.id::text) = :volume_id
                LIMIT 1
                """,
                {"volume_id": vid_search},
            )
            if not header:
                return {"error": "Том не найден.", "report_text": "", "nav_data": {}}

            section_errors: dict[str, str] = {}
            params = {"volume_id": header["id"]}

            bricks: list[dict[str, Any]] = []
            try:
                bricks = insp.fetch_all(
                    """
                    SELECT
                        b.id::text,
                        b.brick_dir,
                        b.vds_name,
                        b.interface_address,
                        b.status AS brick_status,
                        b.is_arbiter,
                        bd.used_space AS brick_used,
                        bd.total_space AS brick_total
                    FROM gluster_volume_bricks_view b
                    LEFT JOIN gluster_volume_brick_details bd
                           ON b.id::text = bd.brick_id::text
                    WHERE b.volume_id::text = :volume_id
                    ORDER BY b.brick_order
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["bricks"] = str(exc)

            options: list[dict[str, Any]] = []
            try:
                options = insp.fetch_all(
                    """
                    SELECT option_key, option_val
                    FROM gluster_volume_options
                    WHERE volume_id::text = :volume_id
                    ORDER BY option_key
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["options"] = str(exc)

            georep: list[dict[str, Any]] = []
            try:
                georep = insp.fetch_all(
                    """
                    SELECT
                        ggs.slave_host_name,
                        ggs.slave_volume_name,
                        ggs.status AS geo_status,
                        ggs.user_name,
                        ggsd.checkpoint_status,
                        ggsd.data_pending,
                        ggsd.last_synced_at
                    FROM gluster_georep_session ggs
                    LEFT JOIN gluster_georep_session_details ggsd
                           ON ggs.session_id = ggsd.session_id
                    WHERE ggs.master_volume_id::text = :volume_id
                    ORDER BY ggs.slave_host_name
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["georep"] = str(exc)

            snapshots: list[dict[str, Any]] = []
            try:
                snapshots = insp.fetch_all(
                    """
                    SELECT snapshot_name, description, status, _create_date
                    FROM gluster_volume_snapshots
                    WHERE volume_id::text = :volume_id
                    ORDER BY _create_date DESC
                    """,
                    params,
                )
            except Exception as exc:
                section_errors["snapshots"] = str(exc)

            payload = {
                "generated_at": now_naive.strftime("%d.%m.%Y %H:%M:%S"),
                "header": header,
                "bricks": bricks,
                "options": options,
                "georep": georep,
                "snapshots": snapshots,
                "section_errors": section_errors,
                "nav_data": {
                    "volume_id": header["id"],
                    "volume_name": header.get("vol_name"),
                    "cluster_name": header.get("cluster_name"),
                },
            }
            payload["report_text"] = format_gluster_report(payload)
            return payload

    except Exception as exc:
        return {"error": f"Ошибка инспектора: {exc}", "report_text": "", "nav_data": {}}

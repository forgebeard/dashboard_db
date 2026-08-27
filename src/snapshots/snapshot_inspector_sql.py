# src/snapshots/snapshot_inspector_sql.py
"""
Модуль генерации диагностического отчета по снапшотам ВМ (Snapshot-Inspector).
Использует InspectorBase для подключения через SQLAlchemy.
"""

from datetime import datetime
import html

from core.constants import IMAGE_STATUS_MAP
from core.inspector_base import InspectorBase


def _safe_text(value: str | None) -> str:
    """Экранирует HTML-спецсимволы для безопасного вывода в отчете."""
    if value is None:
        return "—"
    return html.escape(str(value))


def _fmt_size(bytes_val: int | None) -> str:
    """Форматирует размер из байт в ГБ."""
    if bytes_val is None:
        return "—"
    return f"{round(bytes_val / (1024**3), 2)} ГБ"


def _safe_date(dt):
    """Приводит дату к naive-формату без tzinfo."""
    if not dt:
        return None
    return dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt


def _fmt_date(dt) -> str:
    """Форматирует дату в читаемый вид."""
    if not dt:
        return "—"
    return _safe_date(dt).strftime("%d.%m.%Y %H:%M:%S")


def get_snapshot_inspector_report(db_name: str, vm_id: str) -> dict:
    """
    Возвращает словарь с текстовым отчетом по снапшотам и чекпоинтам ВМ.
    """
    vm_search = str(vm_id).strip().lower()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)

            vm_row = insp.fetch_one(
                "SELECT vm_name FROM vm_static WHERE vm_guid::text = :vm_search LIMIT 1",
                {"vm_search": vm_search},
            )
            if not vm_row:
                return {"error": "ВМ не найдена.", "report_text": "", "nav_data": {}}

            vm_name = vm_row["vm_name"]

            report_lines = [
                "═" * 78,
                f"  Snapshot-Inspector — Диагностический отчёт",
                f"  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}",
                "═" * 78,
                "",
                f"  ВМ: {_safe_text(vm_name)}",
                f"  UUID: {vm_search}",
                "",
            ]

            snapshots = insp.fetch_all(
                """
                SELECT
                    s.snapshot_id::text,
                    s.creation_date,
                    s.description AS snapshot_desc,
                    s.snapshot_type,
                    s.status AS snapshot_status,
                    i.image_guid::text,
                    i.size,
                    i.imagestatus,
                    sd.storage_name,
                    i.active
                FROM snapshots s
                LEFT JOIN images i ON s.snapshot_id = i.vm_snapshot_id
                LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
                LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
                WHERE s.vm_id::text = :vm_search
                ORDER BY s.creation_date DESC
                """,
                {"vm_search": vm_search},
            )

            report_lines.append("СНАПШОТЫ И ОБРАЗЫ ДИСКОВ")
            report_lines.append("─" * 78)

            if not snapshots:
                report_lines.append("    Пользовательские снапшоты отсутствуют.")
            else:
                current_snap = None
                for snap in snapshots:
                    if snap["snapshot_id"] != current_snap:
                        current_snap = snap["snapshot_id"]
                        created = _fmt_date(snap["creation_date"])
                        snap_type = _safe_text(snap["snapshot_type"])
                        snap_status = _safe_text(snap["snapshot_status"])
                        desc = _safe_text(snap["snapshot_desc"]) or "—"

                        report_lines.append(f"\n   📸 Снапшот: {current_snap[:8]}...")
                        report_lines.append(f"    Создан:       {created}")
                        report_lines.append(f"    Тип:          {snap_type}")
                        report_lines.append(f"    Статус:       {snap_status}")
                        report_lines.append(f"    Описание:     {desc}")
                        report_lines.append(f"    {'─'*60}")

                    if snap["image_guid"]:
                        status_label = IMAGE_STATUS_MAP.get(
                            snap["imagestatus"],
                            f"Code {snap['imagestatus']}",
                        )
                        active_marker = " ★ ACTIVE" if snap["active"] else ""
                        storage = _safe_text(snap["storage_name"]) or "Unknown Storage"

                        report_lines.append(
                            f"      💾 Образ: {snap['image_guid'][:8]}...{active_marker}"
                        )
                        report_lines.append(f"         Размер:     {_fmt_size(snap['size'])}")
                        report_lines.append(f"         Статус:     {status_label}")
                        report_lines.append(f"         Хранилище:  {storage}")
                        report_lines.append("")

            checkpoints = insp.fetch_all(
                """
                SELECT
                    cp.checkpoint_id::text,
                    cp.parent_id::text,
                    cp._create_date,
                    cp.state,
                    cp.description
                FROM vm_checkpoints cp
                WHERE cp.vm_id::text = :vm_search
                ORDER BY cp._create_date DESC
                """,
                {"vm_search": vm_search},
            )

            report_lines.append("\nЧЕКПОИНТЫ (LIVE SNAPSHOTS)")
            report_lines.append("─" * 78)

            if not checkpoints:
                report_lines.append("    Чекпоинты отсутствуют.")
            else:
                for cp in checkpoints:
                    created = _fmt_date(cp["_create_date"])
                    state = _safe_text(cp["state"])
                    parent = cp["parent_id"][:8] + "..." if cp["parent_id"] else "Root"
                    desc = _safe_text(cp["description"]) or "—"

                    report_lines.append(f"\n   ⚡ Чекпоинт: {cp['checkpoint_id'][:8]}...")
                    report_lines.append(f"    Создан:       {created}")
                    report_lines.append(f"    Состояние:    {state}")
                    report_lines.append(f"    Родитель:     {parent}")
                    report_lines.append(f"    Описание:     {desc}")

            issues = []
            locked_count = 0
            illegal_count = 0

            for snap in snapshots:
                if snap["imagestatus"] == 2:
                    locked_count += 1
                elif snap["imagestatus"] == 3:
                    illegal_count += 1

            if locked_count > 0:
                issues.append(f" LOCKED образов: {locked_count}")
            if illegal_count > 0:
                issues.append(f"🔴 ILLEGAL образов: {illegal_count}")

            report_lines.append(f"\nДИАГНОСТИКА ({len(issues)} проблем)")
            report_lines.append("─" * 78)
            if issues:
                for issue in issues:
                    report_lines.append(f"    {issue}")
            else:
                report_lines.append("    Критичных проблем с образами не обнаружено")

            report_lines.append("\n" + "═" * 78)

            nav_data = {
                "vm_id": vm_search,
                "vm_name": vm_name,
                "snapshot_count": len(snapshots),
                "checkpoint_count": len(checkpoints),
            }

            return {
                "report_text": "\n".join(report_lines),
                "nav_data": nav_data,
            }

    except Exception as e:
        return {"error": f"Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}

# src/storage/storage_inspector_sql.py
"""
Модуль генерации диагностического отчета по хранилищу (Storage-Inspector).
Использует InspectorBase для подключения через SQLAlchemy.
"""

from datetime import datetime
import traceback

from core.constants import (
    STORAGE_DOMAIN_TYPE_MAP,
    STORAGE_TYPE_MAP,
    IMAGE_STATUS_MAP,
    SHARED_STATUS_MAP,
    HOST_STATUS_MAP,
    VM_STATUS_MAP,
)
from core.inspector_base import InspectorBase


def _fmt_size_gb(val):
    """Форматирует значение ГБ."""
    if val is None:
        return "—"
    try:
        return f"{int(float(val))} ГБ"
    except (ValueError, TypeError):
        return "—"


def _safe_date(dt):
    if not dt:
        return None
    return dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt


def _fmt_date(dt):
    if not dt:
        return "—"
    return _safe_date(dt).strftime("%d.%m.%Y %H:%M:%S")


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
                    sds.storage AS storage_path,
                    sdd.available_disk_size,
                    sdd.used_disk_size,
                    sdss.status as shared_status_code,
                    sp.name as dc_name,
                    sp.id::text as pool_id,
                    vd.vds_name as spm_host_name,
                    vdyn.status as spm_host_status
                FROM storage_domain_static sds
                JOIN storage_domain_dynamic sdd ON sds.id = sdd.id
                LEFT JOIN storage_pool_with_storage_domain spwsd ON sds.id = spwsd.storage_id
                LEFT JOIN storage_pool sp ON spwsd.storage_pool_id = sp.id
                LEFT JOIN vds_static vd ON sp.spm_vds_id = vd.vds_id
                LEFT JOIN vds_dynamic vdyn ON vd.vds_id = vdyn.vds_id
                LEFT JOIN storage_domain_shared_status sdss ON sds.id = sdss.storage_id
                WHERE sds.id::text = :sd_search
                LIMIT 1
                """,
                {"sd_search": sd_search},
            )

            if not sd:
                return {"error": "❌ Хранилище не найдено.", "report_text": "", "nav_data": {}}

            total_gb = float(sd["available_disk_size"] or 0)
            used_gb = float(sd["used_disk_size"] or 0)
            free_gb = total_gb - used_gb
            used_pct = round(used_gb / total_gb * 100, 1) if total_gb > 0 else 0

            spm_name = sd["spm_host_name"]
            spm_code = sd["spm_host_status"]
            spm_label = (
                HOST_STATUS_MAP.get(spm_code, f"Code {spm_code}")
                if spm_code is not None
                else "Не назначен"
            )

            sd_type_label = STORAGE_DOMAIN_TYPE_MAP.get(
                sd["storage_domain_type"], f"Type {sd['storage_domain_type']}"
            )
            st_type_label = STORAGE_TYPE_MAP.get(sd["storage_type"], f"Type {sd['storage_type']}")
            shared_status_label = SHARED_STATUS_MAP.get(
                sd["shared_status_code"], f"Code {sd['shared_status_code']}"
            )

            report_lines = [
                "══════════════════════════════════════════════════════════════════════════════",
                f"  STORAGE-Inspector v1.2 — Диагностический отчёт",
                f"  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}",
                "══════════════════════════════════════════════════════════════════════════════",
                "",
                "📋 ОСНОВНАЯ ИНФОРМАЦИЯ",
                "──────────────────────────────────────────────────────────────────────────────",
                f"  Имя домена:     {sd['storage_name']}",
                f"  UUID:           {sd['sd_id']}",
                f"  Дата-центр:     {sd['dc_name'] or '—'}",
                f"  Тип домена:     {sd_type_label}",
                f"  Тип хранилища:  {st_type_label}",
                f"  Путь/Target:    {sd['storage_path'] or '—'}",
                f"  SPM Хост:       {spm_name or 'Не назначен'} [{spm_label}]",
                "",
                "   💾 Ресурсы (ГБ):",
                f"    Всего:      {_fmt_size_gb(total_gb)}",
                f"    Занято:     {_fmt_size_gb(used_gb)} ({used_pct}%)",
                f"    Свободно:   {_fmt_size_gb(free_gb)}",
                "",
                "  📡 Статус:",
                f"    Shared:     {shared_status_label}",
            ]

            bad_images = insp.fetch_all(
                """
                SELECT
                    bd.disk_alias,
                    i.imagestatus,
                    i.size,
                    i.creation_date,
                    vs.description as snap_name,
                    vd.vm_id
                FROM images i
                JOIN base_disks bd ON i.image_group_id = bd.disk_id
                LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
                LEFT JOIN snapshots vs ON i.vm_snapshot_id = vs.snapshot_id
                LEFT JOIN vm_device vd ON bd.disk_id = vd.device_id
                WHERE isdm.storage_domain_id = CAST(:sd_id AS uuid)
                  AND i.imagestatus IN (2, 3, 4)
                ORDER BY i.creation_date DESC
                LIMIT 20
                """,
                {"sd_id": sd["sd_id"]},
            )

            if bad_images:
                report_lines.append("\n⚠️ ПРОБЛЕМНЫЕ ОБРАЗЫ")
                report_lines.append(
                    "──────────────────────────────────────────────────────────────────────────────"
                )
                for img in bad_images:
                    status_icon = IMAGE_STATUS_MAP.get(img["imagestatus"], "Unknown")
                    vm_info = ""
                    if img["vm_id"]:
                        vm_row = insp.fetch_one(
                            "SELECT vm_name FROM vm_static WHERE vm_guid = :vm_id LIMIT 1",
                            {"vm_id": img["vm_id"]},
                        )
                        vm_info = f" [ВМ: {vm_row['vm_name']}]" if vm_row else ""

                    size_gb = round(img["size"] / 1024**3, 1) if img["size"] else 0
                    report_lines.append(f"  {status_icon} {img['disk_alias'] or 'NoAlias'}{vm_info}")
                    report_lines.append(
                        f"    Размер: {size_gb} ГБ | Снапшот: {img['snap_name'] or 'Active'} | "
                        f"Создан: {_fmt_date(img['creation_date'])}"
                    )
            else:
                report_lines.append("\n✅ Проблемных образов не обнаружено")

            vms = insp.fetch_all(
                """
                SELECT DISTINCT
                    vs.vm_name,
                    vs.vm_guid::text,
                    vdyn.status as vm_status
                FROM vm_device vd
                JOIN base_disks bd ON vd.device_id = bd.disk_id
                JOIN images i ON i.image_group_id = bd.disk_id
                JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
                JOIN vm_static vs ON vd.vm_id = vs.vm_guid
                LEFT JOIN vm_dynamic vdyn ON vs.vm_guid = vdyn.vm_guid
                WHERE isdm.storage_domain_id = CAST(:sd_id AS uuid)
                ORDER BY vs.vm_name
                LIMIT 20
                """,
                {"sd_id": sd["sd_id"]},
            )

            if vms:
                report_lines.append(f"\n ВМ НА ЭТОМ ХРАНИЛИЩЕ ({len(vms)})")
                report_lines.append(
                    "──────────────────────────────────────────────────────────────────────────────"
                )
                for v in vms:
                    st_icon = VM_STATUS_MAP.get(v["vm_status"], f"Code {v['vm_status']}")
                    report_lines.append(f"  • {v['vm_name']} [{st_icon}]")

            issues = []
            if sd["shared_status_code"] == 3:
                issues.append("🔴 Статус хранилища: PROBLEM")
            if sd["spm_host_status"] in [0, 4, 6, 10]:
                issues.append("🔴 SPM Хост недоступен или в ошибке")
            if used_pct > 90:
                issues.append(f"🔴 Заполненность критическая: {used_pct}%")
            elif used_pct > 80:
                issues.append(f"🟡 Заполненность высокая: {used_pct}%")
            if bad_images:
                issues.append(f"🔴 Проблемных образов: {len(bad_images)}")

            report_lines.append(f"\n🔍 ДИАГНОСТИКА ({len(issues)} проблем)")
            report_lines.append(
                "──────────────────────────────────────────────────────────────────────────────"
            )
            if issues:
                for issue in issues:
                    report_lines.append(f"  {issue}")
            else:
                report_lines.append("  ✅ Критичных проблем не обнаружено")

            report_lines.append(
                "\n══════════════════════════════════════════════════════════════════════════════"
            )

            nav_data = {
                "pool_id": sd["pool_id"],
                "dc_name": sd["dc_name"],
                "spm_host_name": sd["spm_host_name"],
            }

            return {
                "report_text": "\n".join(report_lines),
                "nav_data": nav_data,
            }

    except Exception as e:
        return {
            "error": f"❌ Ошибка инспектора: {e}\n{traceback.format_exc()}",
            "report_text": "",
            "nav_data": {},
        }

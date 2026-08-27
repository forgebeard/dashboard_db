# src/disks/disks_inspector_sql.py
"""
Модуль генерации диагностического отчета по Диску/Образу (Disk-Inspector).
Использует InspectorBase для безопасного подключения через SQLAlchemy.
"""

from __future__ import annotations

import traceback        # Форматирование стека вызовов при ошибках
from datetime import datetime  # Работа с датой/временем для форматирования
from typing import Any

from sqlalchemy import text  # Параметризованные запросы

from core.constants import IMAGE_STATUS_MAP, VM_STATUS_MAP  # Глобальные справочники статусов
from core.inspector_base import InspectorBase  # Единая абстракция подключения к БД


def _fmt_size_gb(val: Any) -> str:
    """Форматирует значение байт в ГБ для отображения в отчёте."""
    if val is None:
        return "—"
    try:
        return f"{float(val) / (1024**3):.2f} ГБ"
    except (ValueError, TypeError):
        return "—"


def _fmt_date(dt: Any) -> str:
    """
    Форматирует дату в читаемый вид для текстового отчёта.
    Приводит tz-aware datetime к naive-формату перед strftime.
    """
    if not dt:
        return "—"
    naive_dt = dt.replace(tzinfo=None) if hasattr(dt, "replace") else dt
    return naive_dt.strftime("%d.%m.%Y %H:%M:%S")


def get_disk_inspector_report(db_name: str, image_guid: str) -> dict:
    """
    Возвращает словарь с отчетом по конкретному образу диска.

    Args:
        db_name: Имя базы данных (дампа)
        image_guid: UUID образа диска

    Returns:
        Словарь с ключами: report_text, nav_data, error (при неудаче)
    """
    # Нормализация UUID для сравнения с текстовым представлением в БД
    img_search = str(image_guid).strip()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)

            # ─── 1. Основная информация об образе и его родителе (Диске) ───
            # Множественные LEFT JOIN для получения полной картины привязок:
            #   base_disks — метаданные диска
            #   disk_image_dynamic — фактический размер на хранилище
            #   storage_domain_static — имя хранилища
            #   snapshots — имя снапшота, к которому привязан образ
            #   vm_device + vm_static + vm_dynamic — привязка к ВМ и её статус
            img = insp.fetch_one(
                """
                SELECT
                    i.image_guid::text,
                    i.image_group_id::text as disk_id,
                    bd.disk_alias,
                    i.imagestatus,
                    i.size as virt_size,
                    did.actual_size,
                    i.active,
                    i.creation_date,
                    vs.description as snap_name,
                    sd.storage_name,
                    vm.vm_name,
                    vm.vm_guid::text as vm_id,
                    vdyn.status as vm_status_code
                FROM images i
                JOIN base_disks bd ON i.image_group_id = bd.disk_id
                LEFT JOIN disk_image_dynamic did ON i.image_guid = did.image_id
                LEFT JOIN image_storage_domain_map isdm ON i.image_guid = isdm.image_id
                LEFT JOIN storage_domain_static sd ON isdm.storage_domain_id = sd.id
                LEFT JOIN snapshots vs ON i.vm_snapshot_id = vs.snapshot_id
                LEFT JOIN vm_device vd ON bd.disk_id = vd.device_id
                LEFT JOIN vm_static vm ON vd.vm_id = vm.vm_guid
                LEFT JOIN vm_dynamic vdyn ON vm.vm_guid = vdyn.vm_guid
                WHERE i.image_guid::text = :image_guid
                LIMIT 1
                """,
                {"image_guid": img_search},
            )

            if not img:
                return {"error": "❌ Образ не найден.", "report_text": "", "nav_data": {}}

            # Маппинг числовых кодов статусов в человекочитаемые строки
            status_label = IMAGE_STATUS_MAP.get(img["imagestatus"], f"Code {img['imagestatus']}")
            vm_status_label = (
                VM_STATUS_MAP.get(img["vm_status_code"], f"Code {img['vm_status_code']}")
                if img["vm_status_code"] is not None
                else "—"
            )

            # Формирование заголовка и основной секции отчёта
            report_lines = [
                "══════════════════════════════════════════════════════════════════════════════",
                "  DISK-Inspector v1.0 — Диагностический отчёт образа",
                f"  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}",
                "══════════════════════════════════════════════════════════════════════════════",
                "",
                "📋 ИНФОРМАЦИЯ ОБ ОБРАЗЕ",
                "──────────────────────────────────────────────────────────────────────────────",
                f"  UUID образа:    {img['image_guid']}",
                f"  UUID диска:     {img['disk_id']}",
                f"  Имя диска:      {img['disk_alias'] or '—'}",
                f"  Снапшот:        {img['snap_name'] or 'Active'}",
                f"  Статус:         {status_label}",
                f"  Активен:        {'Да' if img['active'] else 'Нет'}",
                f"  Создан:         {_fmt_date(img['creation_date'])}",
                "",
                "   💾 Размеры:",
                f"    Виртуальный:  {_fmt_size_gb(img['virt_size'])}",
                f"    Фактический:  {_fmt_size_gb(img['actual_size'])}",
                "",
                "   📍 Расположение:",
                f"    Хранилище:    {img['storage_name'] or '—'}",
                "",
                "   💻 Привязка к ВМ:",
                f"    ВМ:           {img['vm_name'] or 'Не привязан'}",
                f"    Статус ВМ:    {vm_status_label}",
            ]

            # ─── 2. Цепочка снапшотов этого диска ──────────────────────
            # Выборка всех образов одного диска (image_group_id) для построения
            # полной цепочки снапшотов. ::uuid необходимо для явного приведения типа.
            chain = insp.fetch_all(
                """
                SELECT
                    i.image_guid::text,
                    vs.description as snap_name,
                    i.imagestatus,
                    i.active,
                    i.creation_date,
                    did.actual_size
                FROM images i
                LEFT JOIN snapshots vs ON i.vm_snapshot_id = vs.snapshot_id
                LEFT JOIN disk_image_dynamic did ON i.image_guid = did.image_id
                WHERE i.image_group_id = CAST(:disk_id AS uuid)
                ORDER BY i.creation_date ASC
                """,
                {"disk_id": img["disk_id"]},
            )

            if chain:
                report_lines.append("\n🔗 ЦЕПОЧКА СНАПШОТОВ ДИСКА")
                report_lines.append("──────────────────────────────────────────────────────────────────────────────")
                for c in chain:
                    # ★ помечает активный образ в цепочке
                    st_icon = "★" if c["active"] else " "
                    st_status = IMAGE_STATUS_MAP.get(c["imagestatus"], "?")
                    report_lines.append(
                        f"  {st_icon} {_fmt_date(c['creation_date'])} | {c['snap_name'] or 'Active':<20} | "
                        f"Статус: {st_status:<8} | Факт: {_fmt_size_gb(c['actual_size'])}"
                    )

            # ─── 3. Активные задачи (Tasks), связанные с этим образом ──
            # В oVirt Engine задачи хранятся в async_tasks, связь с объектами —
            # через async_tasks_entities (entity_id = UUID образа диска)
            # Колонка времени: started_at (не start_time)
            tasks = insp.fetch_all(
                """
                SELECT
                    at.task_id::text,
                    at.action_type,
                    at.status,
                    at.started_at
                FROM async_tasks at
                JOIN async_tasks_entities ate ON at.task_id = ate.async_task_id
                WHERE ate.entity_id = CAST(:image_guid AS uuid)
                ORDER BY at.started_at DESC
                LIMIT 10
                """,
                {"image_guid": img["image_guid"]},
            )

            if tasks:
                report_lines.append(f"\n⚡ СВЯЗАННЫЕ ЗАДАЧИ ({len(tasks)})")
                report_lines.append("──────────────────────────────────────────────────────────────────────────────")
                for t in tasks:
                    report_lines.append(f"  • {t['action_type']} [{t['status']}] - {_fmt_date(t['start_time'])}")

            # ─── 4. Диагностика ────────────────────────────────────────
            # Проверка типовых проблем со статусом образа
            issues = []
            if img["imagestatus"] == 2:
                issues.append("🔴 Образ заблокирован (LOCKED)")
            if img["imagestatus"] == 3:
                issues.append("🔴 Образ поврежден (ILLEGAL)")
            if img["imagestatus"] == 4:
                issues.append("🟡 Идет слияние (MERGING)")

            report_lines.append(f"\n🔍 ДИАГНОСТИКА ({len(issues)} проблем)")
            report_lines.append("──────────────────────────────────────────────────────────────────────────────")
            if issues:
                for issue in issues:
                    report_lines.append(f"  {issue}")
            else:
                report_lines.append("  ✅ Критичных проблем с образом не обнаружено")

            report_lines.append("\n══════════════════════════════════════════════════════════════════════════════")

            # Навигационные данные для связывания с другими инспекторами
            nav_data = {
                "vm_id": img["vm_id"],
                "vm_name": img["vm_name"],
                "disk_id": img["disk_id"],
            }

            return {
                "report_text": "\n".join(report_lines),
                "nav_data": nav_data,
            }

    except Exception as e:
        # Единая точка обработки ошибок с полным стектрейсом для отладки
        return {"error": f"❌ Ошибка инспектора: {e}\n{traceback.format_exc()}", "report_text": "", "nav_data": {}}
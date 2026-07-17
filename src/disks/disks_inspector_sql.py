# src/disks/disks_inspector_sql.py
"""
Модуль генерации диагностического отчета по Диску/Образу (Disk-Inspector).
Использует прямое подключение psycopg2 для сложных выборок.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения
from datetime import datetime  # Работа с датой/временем

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА ---
from core.constants import IMAGE_STATUS_MAP, VM_STATUS_MAP  # Глобальные справочники

def _fmt_size_gb(val):
    """Форматирует значение байт в ГБ."""
    if val is None: return "—"
    try:
        return f"{float(val) / (1024**3):.2f} ГБ"
    except (ValueError, TypeError):
        return "—"

def _fmt_date(dt):
    if not dt: return "—"
    naive_dt = dt.replace(tzinfo=None) if hasattr(dt, 'replace') else dt
    return naive_dt.strftime('%d.%m.%Y %H:%M:%S')

def get_disk_inspector_report(db_name: str, image_guid: str) -> dict:
    """Возвращает словарь с отчетом по конкретному образу диска."""
    img_search = str(image_guid).strip()
    
    conn_params = {
        "dbname": db_name,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    try:
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        now_naive = datetime.now().replace(tzinfo=None)

        # 1. Основная информация об образе и его родителе (Диске)
        cur.execute("""
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
            WHERE i.image_guid::text = %s
            LIMIT 1
        """, (img_search,))
        
        img = cur.fetchone()
        if not img: 
            cur.close(); conn.close()
            return {"error": "❌ Образ не найден.", "report_text": "", "nav_data": {}}

        status_label = IMAGE_STATUS_MAP.get(img['imagestatus'], f"Code {img['imagestatus']}")
        vm_status_label = VM_STATUS_MAP.get(img['vm_status_code'], f"Code {img['vm_status_code']}") if img['vm_status_code'] is not None else "—"

        report_lines = [
            "══════════════════════════════════════════════════════════════════════════════",
            f"  DISK-Inspector v1.0 — Диагностический отчёт образа",
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
            f"    Статус ВМ:    {vm_status_label}"
        ]

        # 2. Цепочка снапшотов этого диска
        cur.execute("""
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
            WHERE i.image_group_id = %s::uuid
            ORDER BY i.creation_date ASC
        """, (img['disk_id'],))
        
        chain = cur.fetchall()
        if chain:
            report_lines.append("\n🔗 ЦЕПОЧКА СНАПШОТОВ ДИСКА")
            report_lines.append("──────────────────────────────────────────────────────────────────────────────")
            for c in chain:
                st_icon = "★" if c['active'] else " "
                st_status = IMAGE_STATUS_MAP.get(c['imagestatus'], "?")
                report_lines.append(
                    f"  {st_icon} {_fmt_date(c['creation_date'])} | {c['snap_name'] or 'Active':<20} | "
                    f"Статус: {st_status:<8} | Факт: {_fmt_size_gb(c['actual_size'])}"
                )

        # 3. Активные задачи (Tasks), связанные с этим образом
        cur.execute("""
            SELECT 
                task_id::text,
                action_type,
                status,
                start_time
            FROM tasks
            WHERE related_object_id = %s::uuid OR command_parameters::text LIKE %s
            ORDER BY start_time DESC
            LIMIT 10
        """, (img['image_guid'], f"%{img['image_guid']}%"))
        
        tasks = cur.fetchall()
        if tasks:
            report_lines.append(f"\n⚡ СВЯЗАННЫЕ ЗАДАЧИ ({len(tasks)})")
            report_lines.append("──────────────────────────────────────────────────────────────────────────────")
            for t in tasks:
                report_lines.append(f"  • {t['action_type']} [{t['status']}] - {_fmt_date(t['start_time'])}")

        # 4. Диагностика
        issues = []
        if img['imagestatus'] == 2: issues.append("🔴 Образ заблокирован (LOCKED)")
        if img['imagestatus'] == 3: issues.append("🔴 Образ поврежден (ILLEGAL)")
        if img['imagestatus'] == 4: issues.append("🟡 Идет слияние (MERGING)")
        
        report_lines.append(f"\n🔍 ДИАГНОСТИКА ({len(issues)} проблем)")
        report_lines.append("──────────────────────────────────────────────────────────────────────────────")
        if issues:
            for issue in issues: report_lines.append(f"  {issue}")
        else:
            report_lines.append("  ✅ Критичных проблем с образом не обнаружено")

        report_lines.append("\n══════════════════════════════════════════════════════════════════════════════")
        
        cur.close()
        conn.close()

        nav_data = {
            "vm_id": img['vm_id'],
            "vm_name": img['vm_name'],
            "disk_id": img['disk_id']
        }

        return {
            "report_text": "\n".join(report_lines),
            "nav_data": nav_data
        }

    except Exception as e:
        import traceback
        return {"error": f"❌ Ошибка инспектора: {e}\n{traceback.format_exc()}", "report_text": "", "nav_data": {}}
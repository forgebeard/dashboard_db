# src/snapshots/snapshot_inspector_sql.py
"""
Модуль генерации диагностического отчета по снапшотам ВМ (Snapshot-Inspector).
Использует прямое подключение psycopg2 для сложных выборок.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (DB_USER, DB_PASSWORD и др.)
from datetime import datetime  # Работа с датой/временем для форматирования
import html             # Экранирование спецсимволов для безопасности отчета

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL для прямого подключения к БД
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.constants import IMAGE_STATUS_MAP  # Глобальный справочник статусов образов


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
    return dt.replace(tzinfo=None) if hasattr(dt, 'replace') else dt


def _fmt_date(dt) -> str:
    """Форматирует дату в читаемый вид."""
    if not dt:
        return "—"
    return _safe_date(dt).strftime('%d.%m.%Y %H:%M:%S')


def get_snapshot_inspector_report(db_name: str, vm_id: str) -> dict:
    """
    Возвращает словарь с текстовым отчетом по снапшотам и чекпоинтам ВМ.
    
    Args:
        db_name: Имя базы данных (дампа)
        vm_id: UUID виртуальной машины
        
    Returns:
        Словарь с ключами: report_text, nav_data, error (при неудаче)
    """
    vm_search = str(vm_id).strip().lower()
    
    conn_params = {
        "dbname": db_name,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
    }

    try:
        with psycopg2.connect(**conn_params) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                now_naive = datetime.now().replace(tzinfo=None)

                # Проверка существования ВМ
                cur.execute(
                    "SELECT vm_name FROM vm_static WHERE vm_guid::text = %s LIMIT 1", 
                    (vm_search,)
                )
                vm_row = cur.fetchone()
                if not vm_row:
                    return {"error": "ВМ не найдена.", "report_text": "", "nav_data": {}}

                vm_name = vm_row['vm_name']

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

                # 1. Снапшоты + Диски
                cur.execute("""
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
                    WHERE s.vm_id::text = %s
                    ORDER BY s.creation_date DESC
                """, (vm_search,))
                
                snapshots = cur.fetchall()
                
                report_lines.append("СНАПШОТЫ И ОБРАЗЫ ДИСКОВ")
                report_lines.append("─" * 78)
                
                if not snapshots:
                    report_lines.append("    Пользовательские снапшоты отсутствуют.")
                else:
                    current_snap = None
                    for snap in snapshots:
                        if snap['snapshot_id'] != current_snap:
                            current_snap = snap['snapshot_id']
                            created = _fmt_date(snap['creation_date'])
                            snap_type = _safe_text(snap['snapshot_type'])
                            snap_status = _safe_text(snap['snapshot_status'])
                            desc = _safe_text(snap['snapshot_desc']) or "—"
                            
                            report_lines.append(f"\n   📸 Снапшот: {current_snap[:8]}...")
                            report_lines.append(f"    Создан:       {created}")
                            report_lines.append(f"    Тип:          {snap_type}")
                            report_lines.append(f"    Статус:       {snap_status}")
                            report_lines.append(f"    Описание:     {desc}")
                            report_lines.append(f"    {'─'*60}")
                        
                        # Информация об образе диска
                        if snap['image_guid']:
                            status_label = IMAGE_STATUS_MAP.get(
                                snap['imagestatus'], 
                                f"Code {snap['imagestatus']}"
                            )
                            active_marker = " ★ ACTIVE" if snap['active'] else ""
                            storage = _safe_text(snap['storage_name']) or "Unknown Storage"
                            
                            report_lines.append(
                                f"      💾 Образ: {snap['image_guid'][:8]}...{active_marker}"
                            )
                            report_lines.append(
                                f"         Размер:     {_fmt_size(snap['size'])}"
                            )
                            report_lines.append(
                                f"         Статус:     {status_label}"
                            )
                            report_lines.append(
                                f"         Хранилище:  {storage}"
                            )
                            report_lines.append("")

                # 2. Чекпоинты (параллельная сущность)
                cur.execute("""
                    SELECT 
                        cp.checkpoint_id::text,
                        cp.parent_id::text,
                        cp._create_date,
                        cp.state,
                        cp.description
                    FROM vm_checkpoints cp
                    WHERE cp.vm_id::text = %s
                    ORDER BY cp._create_date DESC
                """, (vm_search,))
                
                checkpoints = cur.fetchall()
                
                report_lines.append("\nЧЕКПОИНТЫ (LIVE SNAPSHOTS)")
                report_lines.append("─" * 78)
                
                if not checkpoints:
                    report_lines.append("    Чекпоинты отсутствуют.")
                else:
                    for cp in checkpoints:
                        created = _fmt_date(cp['_create_date'])
                        state = _safe_text(cp['state'])
                        parent = cp['parent_id'][:8] + "..." if cp['parent_id'] else "Root"
                        desc = _safe_text(cp['description']) or "—"
                        
                        report_lines.append(f"\n   ⚡ Чекпоинт: {cp['checkpoint_id'][:8]}...")
                        report_lines.append(f"    Создан:       {created}")
                        report_lines.append(f"    Состояние:    {state}")
                        report_lines.append(f"    Родитель:     {parent}")
                        report_lines.append(f"    Описание:     {desc}")

                # 3. Диагностика проблемных образов
                issues = []
                locked_count = 0
                illegal_count = 0
                
                for snap in snapshots:
                    if snap['imagestatus'] == 2:  # LOCKED
                        locked_count += 1
                    elif snap['imagestatus'] == 3:  # ILLEGAL
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
                    "nav_data": nav_data
                }

    except Exception as e:
        return {"error": f"Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}
# src/tasks/task_inspector_sql.py
"""
Модуль генерации диагностического отчета по задаче VDSM (Task-Inspector).
Использует прямое подключение psycopg2 для сложных выборок и анализа связей 
с командами Engine и журналом аудита.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (DB_USER, DB_PASSWORD и др.)
from datetime import datetime, timedelta  # Работа с датой/временем для поиска смежных событий в audit_log

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL для прямого подключения к БД
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари (удобно для доступа по имени колонки)

def _fmt_date(dt):
    if not dt: return "—"
    return dt.strftime('%d.%m.%Y %H:%M:%S')

def get_task_inspector_report(db_name: str, task_id: str) -> dict:
    """Формирует отчет по задаче VDSM."""
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
        
        # 1. Основная информация о задаче
        cur.execute("""
            SELECT 
                t.task_id::text, t.action_type, t.status, t.result, 
                t.started_at, t.storage_pool_id::text, t.task_type, 
                t.vdsm_task_id, t.root_command_id::text, t.user_id::text,
                c.command_type, c.status as cmd_status, c.created_at,
                c.command_parameters, c.data
            FROM async_tasks t
            LEFT JOIN command_entities c ON t.command_id = c.command_id
            WHERE t.task_id::text = %s LIMIT 1
        """, (task_id,))
        
        task = cur.fetchone()
        if not task:
            cur.close(); conn.close()
            return {"error": "Задача не найдена.", "report_text": ""}

        lines = [
            "══════════════════════════════════════════════════════════════",
            f"  TASK-INSPECTOR — Отчет по задаче #{task['task_id'][:8]}...",
            "══════════════════════════════════════════════════════════════",
            "",
            "📋 ТЕХНИЧЕСКИЕ ПАРАМЕТРЫ",
            "──────────────────────────────────────────────────────────────",
            f"  Тип действия (Code): {task['action_type']}",
            f"  Статус (Code):       {task['status']} (Result: {task['result']})",
            f"  Начато:              {_fmt_date(task['started_at'])}",
            f"  VDSM Task ID:        {task['vdsm_task_id']}",
            f"  Storage Pool:        {task['storage_pool_id']}",
            "",
            "🔗 СВЯЗАННАЯ КОМАНДА (Command Entity)",
            "──────────────────────────────────────────────────────────────",
            f"  Command Type:        {task['command_type']}",
            f"  Command Status:      {task['cmd_status']}",
            f"  Created At:          {_fmt_date(task['created_at'])}",
            "",
            "💬 ДАННЫЕ КОМАНДЫ",
            "──────────────────────────────────────────────────────────────",
        ]
        
        # Вывод параметров (если они есть)
        params = task['command_parameters'] or task['data']
        if params:
            # Обрезаем слишком длинные данные для читаемости
            text_params = str(params)[:1000]
            lines.append(f"  {text_params}")
            if len(str(params)) > 1000:
                lines.append("  ... (данные обрезаны)")
        else:
            lines.append("  (Параметры команды отсутствуют или пусты)")

        # 2. Попытка найти связанные события в Audit Log по времени (± 2 минуты)
        start_time = task['started_at']
        if start_time:
            t_start = start_time - timedelta(minutes=2)
            t_end = start_time + timedelta(minutes=2)
            
            cur.execute("""
                SELECT log_time, log_type_name, vm_name, vds_name, message
                FROM audit_log
                WHERE log_time BETWEEN %s AND %s
                ORDER BY log_time ASC
                LIMIT 5
            """, (t_start, t_end))
            
            related_logs = cur.fetchall()
            if related_logs:
                lines.append("\n🔍 СОПУТСТВУЮЩИЕ СОБЫТИЯ (Audit Log ±2 мин)")
                lines.append("──────────────────────────────────────────────────────────────")
                for log in related_logs:
                    lines.append(f"  [{_fmt_date(log['log_time'])}] {log['log_type_name']}")
                    if log['vm_name']: lines.append(f"    ВМ: {log['vm_name']}")
                    if log['vds_name']: lines.append(f"    Хост: {log['vds_name']}")

        lines.append("\n══════════════════════════════════════════════════════════════")
        
        cur.close()
        conn.close()
        return {"report_text": "\n".join(lines)}

    except Exception as e:
        return {"error": f"❌ Ошибка инспектора задач: {e}", "report_text": ""}
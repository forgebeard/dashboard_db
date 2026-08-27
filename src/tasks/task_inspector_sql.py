# src/tasks/task_inspector_sql.py
"""
Модуль генерации диагностического отчета по задаче VDSM (Task-Inspector).
Использует InspectorBase для подключения через SQLAlchemy.
"""

from datetime import timedelta

from core.inspector_base import InspectorBase


def _fmt_date(dt):
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def get_task_inspector_report(db_name: str, task_id: str) -> dict:
    """Формирует отчет по задаче VDSM."""
    try:
        with InspectorBase(db_name) as insp:
            task = insp.fetch_one(
                """
                SELECT
                    t.task_id::text, t.action_type, t.status, t.result,
                    t.started_at, t.storage_pool_id::text, t.task_type,
                    t.vdsm_task_id, t.root_command_id::text, t.user_id::text,
                    c.command_type, c.status as cmd_status, c.created_at,
                    c.command_parameters, c.data
                FROM async_tasks t
                LEFT JOIN command_entities c ON t.command_id = c.command_id
                WHERE t.task_id::text = :task_id LIMIT 1
                """,
                {"task_id": task_id},
            )

            if not task:
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

            params = task["command_parameters"] or task["data"]
            if params:
                text_params = str(params)[:1000]
                lines.append(f"  {text_params}")
                if len(str(params)) > 1000:
                    lines.append("  ... (данные обрезаны)")
            else:
                lines.append("  (Параметры команды отсутствуют или пусты)")

            start_time = task["started_at"]
            if start_time:
                t_start = start_time - timedelta(minutes=2)
                t_end = start_time + timedelta(minutes=2)

                related_logs = insp.fetch_all(
                    """
                    SELECT log_time, log_type_name, vm_name, vds_name, message
                    FROM audit_log
                    WHERE log_time BETWEEN :t_start AND :t_end
                    ORDER BY log_time ASC
                    LIMIT 5
                    """,
                    {"t_start": t_start, "t_end": t_end},
                )
                if related_logs:
                    lines.append("\n🔍 СОПУТСТВУЮЩИЕ СОБЫТИЯ (Audit Log ±2 мин)")
                    lines.append("──────────────────────────────────────────────────────────────")
                    for log in related_logs:
                        lines.append(f"  [{_fmt_date(log['log_time'])}] {log['log_type_name']}")
                        if log["vm_name"]:
                            lines.append(f"    ВМ: {log['vm_name']}")
                        if log["vds_name"]:
                            lines.append(f"    Хост: {log['vds_name']}")

            lines.append("\n══════════════════════════════════════════════════════════════")
            return {"report_text": "\n".join(lines)}

    except Exception as e:
        return {"error": f"❌ Ошибка инспектора задач: {e}", "report_text": ""}

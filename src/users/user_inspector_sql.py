# src/users/user_inspector_sql.py
"""
Модуль генерации диагностического отчета по пользователю (User-Inspector).
Использует InspectorBase для подключения через SQLAlchemy.
"""

from datetime import datetime
import html
import json

from core.inspector_base import InspectorBase


def _safe_text(value: str | None) -> str:
    """Экранирует HTML-спецсимволы для безопасного вывода в отчете."""
    if value is None:
        return "—"
    return html.escape(str(value))


def get_user_inspector_report(db_name: str, user_id: str) -> dict:
    """Возвращает словарь с текстовым отчетом по пользователю."""
    uid_search = str(user_id).strip().lower()

    try:
        with InspectorBase(db_name) as insp:
            now_naive = datetime.now().replace(tzinfo=None)

            user_row = insp.fetch_one(
                "SELECT name, domain, namespace FROM users WHERE user_id::text = :uid LIMIT 1",
                {"uid": uid_search},
            )
            if not user_row:
                return {"error": "Пользователь не найден.", "report_text": "", "nav_data": {}}

            user_name = user_row["name"] or "(без имени)"
            auth_domain = user_row["domain"]
            namespace = user_row["namespace"]

            report_lines = [
                "═" * 78,
                f"  User-Inspector — Диагностический отчёт",
                f"  Время: {now_naive.strftime('%d.%m.%Y %H:%M:%S')}",
                "═" * 78,
                "",
                "ОСНОВНАЯ ИНФОРМАЦИЯ",
                "─" * 78,
                f"  Имя:            {_safe_text(user_name)}",
                f"  UUID:           {uid_search}",
                f"  Домен:          {_safe_text(auth_domain)}",
                f"  Namespace:      {_safe_text(namespace)}",
                "",
            ]

            profiles = insp.fetch_all(
                """
                SELECT property_name, property_content, property_type
                FROM user_profiles
                WHERE user_id::text = :uid
                ORDER BY property_name
                """,
                {"uid": uid_search},
            )

            report_lines.append("СВОЙСТВА ПРОФИЛЯ")
            report_lines.append("─" * 78)

            if not profiles:
                report_lines.append("    Пользовательские свойства отсутствуют.")
            else:
                for prop in profiles:
                    content = prop["property_content"]
                    if isinstance(content, (dict, list)):
                        display_val = json.dumps(content, ensure_ascii=False, indent=2)
                        display_val = "\n    ".join(display_val.split("\n"))
                    else:
                        display_val = _safe_text(str(content))

                    report_lines.append(f"    {prop['property_name']}:")
                    report_lines.append(f"      {display_val}")
                    report_lines.append("")

            groups = insp.fetch_all(
                """
                SELECT DISTINCT ag.name AS group_name, ag.namespace AS group_namespace
                FROM engine_session_user_flat_groups esg
                JOIN ad_groups ag ON esg.granted_id = ag.id
                WHERE esg.user_id::text = :uid
                ORDER BY ag.name
                """,
                {"uid": uid_search},
            )

            report_lines.append("ГРУППЫ ACTIVE DIRECTORY")
            report_lines.append("─" * 78)

            if not groups:
                report_lines.append("    Членство в группах AD не обнаружено.")
            else:
                for g in groups:
                    ns = _safe_text(g["group_namespace"])
                    report_lines.append(f"      • {_safe_text(g['group_name'])} ({ns})")

            roles = insp.fetch_all(
                """
                SELECT DISTINCT r.name AS role_name
                FROM permissions p
                JOIN roles r ON p.role_id = r.id
                WHERE p.ad_element_id::text = :uid
                ORDER BY r.name
                """,
                {"uid": uid_search},
            )

            report_lines.append("\nСИСТЕМНЫЕ РОЛИ")
            report_lines.append("─" * 78)

            if not roles:
                report_lines.append("    Явные системные роли не назначены.")
            else:
                for r in roles:
                    marker = " ️ ADMIN" if r["role_name"] == "SuperUser" else ""
                    report_lines.append(f"      • {_safe_text(r['role_name'])}{marker}")

            tags = insp.fetch_all(
                """
                SELECT t.tag_name, t.readonly, t.type
                FROM tags_user_map tum
                JOIN tags t ON tum.tag_id = t.tag_id
                WHERE tum.user_id::text = :uid
                ORDER BY t.tag_name
                """,
                {"uid": uid_search},
            )

            report_lines.append("\nТЕГИ ПОЛЬЗОВАТЕЛЯ")
            report_lines.append("─" * 78)

            if not tags:
                report_lines.append("    Теги не назначены.")
            else:
                for tag in tags:
                    ro_marker = " 🔒" if tag["readonly"] else ""
                    report_lines.append(f"    • {_safe_text(tag['tag_name'])}{ro_marker}")

            report_lines.append("\nЗАКЛАДКИ")
            report_lines.append("─" * 78)
            report_lines.append("    Таблица bookmarks не имеет прямой связи с пользователями.")
            report_lines.append("    Для просмотра закладок используйте диагностику раздела.")

            report_lines.append("\n" + "═" * 78)

            nav_data = {
                "user_id": uid_search,
                "user_name": user_name,
                "auth_domain": auth_domain,
            }

            return {
                "report_text": "\n".join(report_lines),
                "nav_data": nav_data,
            }

    except Exception as e:
        return {"error": f"Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}

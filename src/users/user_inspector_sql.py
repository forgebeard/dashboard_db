# src/users/user_inspector_sql.py
"""
Модуль генерации диагностического отчета по пользователю (User-Inspector).
Использует прямое подключение psycopg2 для сложных выборок.
Все SQL-запросы используют только подтвержденные имена столбцов из information_schema.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (DB_USER, DB_PASSWORD и др.)
from datetime import datetime  # Работа с датой/временем для форматирования
import html             # Экранирование спецсимволов для безопасности отчета
import json             # Парсинг JSONB свойств пользователя

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import psycopg2         # Драйвер PostgreSQL для прямого подключения к БД
from psycopg2.extras import RealDictCursor  # Курсор, возвращающий строки как словари


def _safe_text(value: str | None) -> str:
    """Экранирует HTML-спецсимволы для безопасного вывода в отчете."""
    if value is None:
        return "—"
    return html.escape(str(value))


def get_user_inspector_report(db_name: str, user_id: str) -> dict:
    """
    Возвращает словарь с текстовым отчетом по пользователю.
    
    Args:
        db_name: Имя базы данных (дампа)
        user_id: UUID пользователя
        
    Returns:
        Словарь с ключами: report_text, nav_data, error (при неудаче)
    """
    uid_search = str(user_id).strip().lower()
    
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

                # Проверка существования пользователя
                cur.execute(
                    "SELECT name, domain, namespace FROM users WHERE user_id::text = %s LIMIT 1", 
                    (uid_search,)
                )
                user_row = cur.fetchone()
                if not user_row:
                    return {"error": "Пользователь не найден.", "report_text": "", "nav_data": {}}

                user_name = user_row['name'] or "(без имени)"
                auth_domain = user_row['domain']
                namespace = user_row['namespace']

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

                # 1. Свойства профиля (EAV + JSONB)
                cur.execute("""
                    SELECT property_name, property_content, property_type
                    FROM user_profiles
                    WHERE user_id::text = %s
                    ORDER BY property_name
                """, (uid_search,))
                
                profiles = cur.fetchall()
                
                report_lines.append("СВОЙСТВА ПРОФИЛЯ")
                report_lines.append("─" * 78)
                
                if not profiles:
                    report_lines.append("    Пользовательские свойства отсутствуют.")
                else:
                    for prop in profiles:
                        content = prop['property_content']
                        if isinstance(content, (dict, list)):
                            display_val = json.dumps(content, ensure_ascii=False, indent=2)
                            display_val = "\n    ".join(display_val.split("\n"))
                        else:
                            display_val = _safe_text(str(content))
                            
                        report_lines.append(f"    {prop['property_name']}:")
                        report_lines.append(f"      {display_val}")
                        report_lines.append("")

                # 2. Группы AD (через granted_id + JOIN к ad_groups)
                cur.execute("""
                    SELECT DISTINCT ag.name AS group_name, ag.namespace AS group_namespace
                    FROM engine_session_user_flat_groups esg
                    JOIN ad_groups ag ON esg.granted_id = ag.id
                    WHERE esg.user_id::text = %s
                    ORDER BY ag.name
                """, (uid_search,))
                
                groups = cur.fetchall()
                
                report_lines.append("ГРУППЫ ACTIVE DIRECTORY")
                report_lines.append("─" * 78)
                
                if not groups:
                    report_lines.append("    Членство в группах AD не обнаружено.")
                else:
                    for g in groups:
                        ns = _safe_text(g['group_namespace'])
                        report_lines.append(f"      • {_safe_text(g['group_name'])} ({ns})")

                # 3. Системные роли (через ad_element_id)
                cur.execute("""
                    SELECT DISTINCT r.name AS role_name
                    FROM permissions p
                    JOIN roles r ON p.role_id = r.id
                    WHERE p.ad_element_id::text = %s
                    ORDER BY r.name
                """, (uid_search,))
                
                roles = cur.fetchall()
                
                report_lines.append("\nСИСТЕМНЫЕ РОЛИ")
                report_lines.append("─" * 78)
                
                if not roles:
                    report_lines.append("    Явные системные роли не назначены.")
                else:
                    for r in roles:
                        marker = " ️ ADMIN" if r['role_name'] == 'SuperUser' else ""
                        report_lines.append(f"      • {_safe_text(r['role_name'])}{marker}")

                # 4. Теги пользователя
                cur.execute("""
                    SELECT t.tag_name, t.readonly, t.type
                    FROM tags_user_map tum
                    JOIN tags t ON tum.tag_id = t.tag_id
                    WHERE tum.user_id::text = %s
                    ORDER BY t.tag_name
                """, (uid_search,))
                
                tags = cur.fetchall()
                
                report_lines.append("\nТЕГИ ПОЛЬЗОВАТЕЛЯ")
                report_lines.append("─" * 78)
                
                if not tags:
                    report_lines.append("    Теги не назначены.")
                else:
                    for tag in tags:
                        ro_marker = " 🔒" if tag['readonly'] else ""
                        report_lines.append(f"    • {_safe_text(tag['tag_name'])}{ro_marker}")

                # 5. Закладки (таблица bookmarks не имеет поля user_id)
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
                    "nav_data": nav_data
                }

    except Exception as e:
        return {"error": f"Ошибка инспектора: {e}", "report_text": "", "nav_data": {}}
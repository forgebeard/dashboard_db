"""Проверки ad-hoc SQL: только чтение и потолок строк."""

from __future__ import annotations

import re

_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"--.*?$", re.MULTILINE)
_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"COPY|CALL|DO|EXECUTE|MERGE|REFRESH|VACUUM|INTO|LOCK|LOAD|"
    r"NOTIFY|LISTEN|UNLISTEN|SECURITY|RESET|SET"
    r")\b",
    re.IGNORECASE,
)
_LEADING_EXPLAIN = re.compile(
    r"^\s*EXPLAIN(?:\s+ANALYZE)?(?:\s+VERBOSE)?\s+",
    re.IGNORECASE,
)


def strip_sql_comments(sql: str) -> str:
    cleaned = _COMMENT_BLOCK.sub(" ", sql)
    cleaned = _COMMENT_LINE.sub(" ", cleaned)
    return cleaned.strip()


def validate_adhoc_sql(sql: str) -> str:
    """
    Принимает один SELECT/WITH (опционально EXPLAIN/SHOW/TABLE/VALUES).
    Возвращает очищенный стейтмент без хвостовой точки с запятой.
    """
    cleaned = strip_sql_comments(sql)
    if not cleaned:
        raise ValueError("Пустой SQL-запрос.")

    cleaned = cleaned.rstrip().rstrip(";").strip()
    if not cleaned:
        raise ValueError("Пустой SQL-запрос.")
    if ";" in cleaned:
        raise ValueError("Разрешён только один SQL-стейтмент (без ';').")

    body = cleaned
    explain_prefix = ""
    explain_match = _LEADING_EXPLAIN.match(body)
    if explain_match:
        explain_prefix = body[: explain_match.end()]
        body = body[explain_match.end() :].strip()
        if not body:
            raise ValueError("После EXPLAIN нужен SELECT или WITH.")

    first = body.split(None, 1)[0].upper()
    if first not in {"SELECT", "WITH", "TABLE", "SHOW", "VALUES"}:
        raise ValueError(
            "Разрешены только запросы на чтение: SELECT, WITH … SELECT, "
            "TABLE, SHOW, VALUES или EXPLAIN к ним."
        )

    if first == "WITH" and not re.search(r"\bSELECT\b", body, re.IGNORECASE):
        raise ValueError("WITH-запрос должен содержать SELECT.")

    if _FORBIDDEN.search(body):
        raise ValueError(
            "Запрос содержит команды изменения данных. "
            "Редактор работает только на чтение."
        )

    return f"{explain_prefix}{body}".strip()


def apply_max_row_limit(sql: str, limit: int) -> str:
    """Оборачивает выборку внешним LIMIT. EXPLAIN и SHOW не оборачиваются."""
    cap = int(limit)
    first = sql.split(None, 1)[0].upper()
    if first in {"EXPLAIN", "SHOW"}:
        return sql
    return f"SELECT * FROM (\n{sql}\n) AS _query_limit LIMIT {cap}"

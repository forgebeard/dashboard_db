"""Проверки ad-hoc SQL: только чтение и потолок строк."""

from __future__ import annotations

import re

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
_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$")


def _append_literal(executable: list[str], skeleton: list[str], chunk: str) -> None:
    executable.append(chunk)
    skeleton.append(" " * len(chunk))


def _scan_quoted(
    sql: str, start: int, quote: str
) -> tuple[int, str]:
    """Возвращает индекс после закрывающей кавычки и сам литерал."""
    i = start + 1
    n = len(sql)
    while i < n:
        if sql[i] == quote:
            if i + 1 < n and sql[i + 1] == quote:
                i += 2
                continue
            return i + 1, sql[start : i + 1]
        i += 1
    return n, sql[start:]


def _scan_dollar_quote(sql: str, start: int) -> tuple[int, str] | None:
    n = len(sql)
    if start >= n or sql[start] != "$":
        return None
    if start + 1 < n and sql[start + 1] == "$":
        tag = "$$"
        tag_end = start + 2
    else:
        match = _DOLLAR_TAG.match(sql, start)
        if not match:
            return None
        tag = match.group(0)
        tag_end = match.end()
    close = sql.find(tag, tag_end)
    if close == -1:
        return n, sql[start:]
    end = close + len(tag)
    return end, sql[start:end]


def _lex_sql(sql: str) -> tuple[str, str]:
    """Текст без комментариев и скелет, где литералы заменены пробелами."""
    executable: list[str] = []
    skeleton: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if ch == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] != "\n":
                i += 1
            continue

        if ch == "/" and nxt == "*":
            i += 2
            depth = 1
            while i < n and depth:
                if i + 1 < n and sql[i] == "/" and sql[i + 1] == "*":
                    depth += 1
                    i += 2
                    continue
                if i + 1 < n and sql[i] == "*" and sql[i + 1] == "/":
                    depth -= 1
                    i += 2
                    continue
                i += 1
            executable.append(" ")
            skeleton.append(" ")
            continue

        if ch in {"'", '"'}:
            i, chunk = _scan_quoted(sql, i, ch)
            _append_literal(executable, skeleton, chunk)
            continue

        dollar = _scan_dollar_quote(sql, i)
        if dollar is not None:
            i, chunk = dollar
            _append_literal(executable, skeleton, chunk)
            continue

        executable.append(ch)
        skeleton.append(ch)
        i += 1

    return "".join(executable), "".join(skeleton)


def _trim_pair(executable: str, skeleton: str) -> tuple[str, str]:
    start = 0
    end = len(executable)
    while start < end and executable[start].isspace():
        start += 1
    while end > start and executable[end - 1].isspace():
        end -= 1
    return executable[start:end], skeleton[start:end]


def _strip_trailing_semicolons(executable: str, skeleton: str) -> tuple[str, str]:
    executable, skeleton = _trim_pair(executable, skeleton)
    while executable.endswith(";"):
        executable, skeleton = _trim_pair(executable[:-1], skeleton[:-1])
    return executable, skeleton


def strip_sql_comments(sql: str) -> str:
    cleaned, _ = _lex_sql(sql)
    return cleaned.strip()


def validate_adhoc_sql(sql: str) -> str:
    """
    Принимает один SELECT/WITH (опционально EXPLAIN/SHOW/TABLE/VALUES).
    Возвращает очищенный стейтмент без хвостовой точки с запятой.
    """
    executable, skeleton = _lex_sql(sql)
    executable, skeleton = _strip_trailing_semicolons(executable, skeleton)
    if not executable:
        raise ValueError("Пустой SQL-запрос.")
    if ";" in skeleton:
        raise ValueError("Разрешён только один SQL-стейтмент (без ';').")

    body_exec = executable
    body_skel = skeleton
    explain_prefix = ""
    explain_match = _LEADING_EXPLAIN.match(body_skel)
    if explain_match:
        cut = explain_match.end()
        explain_prefix = body_exec[:cut]
        body_exec, body_skel = _trim_pair(body_exec[cut:], body_skel[cut:])
        if not body_exec:
            raise ValueError("После EXPLAIN нужен SELECT или WITH.")

    first = body_skel.split(None, 1)[0].upper()
    if first not in {"SELECT", "WITH", "TABLE", "SHOW", "VALUES"}:
        raise ValueError(
            "Разрешены только запросы на чтение: SELECT, WITH … SELECT, "
            "TABLE, SHOW, VALUES или EXPLAIN к ним."
        )

    if first == "WITH" and not re.search(r"\bSELECT\b", body_skel, re.IGNORECASE):
        raise ValueError("WITH-запрос должен содержать SELECT.")

    if _FORBIDDEN.search(body_skel):
        raise ValueError(
            "Запрос содержит команды изменения данных. "
            "Редактор работает только на чтение."
        )

    return f"{explain_prefix}{body_exec}".strip()


def apply_max_row_limit(sql: str, limit: int) -> str:
    """Оборачивает выборку внешним LIMIT. EXPLAIN и SHOW не оборачиваются."""
    cap = int(limit)
    first = sql.split(None, 1)[0].upper()
    if first in {"EXPLAIN", "SHOW"}:
        return sql
    return f"SELECT * FROM (\n{sql}\n) AS _query_limit LIMIT {cap}"

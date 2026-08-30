"""Юнит-тесты для src/core/sql_guard.py."""
import pytest

from core.sql_guard import apply_max_row_limit, validate_adhoc_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM vm_static LIMIT 10",
        "select 1",
        "WITH x AS (SELECT 1 AS n) SELECT * FROM x",
        "EXPLAIN SELECT * FROM vds_static",
        "EXPLAIN ANALYZE SELECT 1",
        "TABLE vm_static",
        "SHOW default_transaction_read_only",
        "VALUES (1), (2)",
        "SELECT * FROM vm_static;   ",
        "-- comment\nSELECT 1",
        "SELECT 1 /* block */",
        "SELECT 1 /* outer /* inner */ outer */",
        "SELECT 'text -- not a comment'",
        "SELECT 'DELETE'",
        "SELECT 'a;b'",
        "SELECT $$ text /* not a comment */ $$",
        "SELECT $tag$ DELETE ; -- still literal $tag$",
        'SELECT "INTO"',
        r"SELECT e'text -- x'",
    ],
)
def test_validate_allows_reads(sql):
    result = validate_adhoc_sql(sql)
    assert result
    assert not result.endswith(";")


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO vm_static VALUES (1)",
        "UPDATE vds_static SET vds_name = 'x'",
        "DELETE FROM audit_log",
        "DROP TABLE vm_static",
        "ALTER TABLE vm_static ADD COLUMN x int",
        "CREATE TABLE t (id int)",
        "SELECT 1; SELECT 2",
        "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x",
        "",
        "   ",
        "EXPLAIN",
        "VACUUM vm_static",
    ],
)
def test_validate_rejects_writes(sql):
    with pytest.raises(ValueError):
        validate_adhoc_sql(sql)


def test_validate_allows_e_string_with_escaped_quote():
    sql = r"SELECT E'a\';b'"
    assert validate_adhoc_sql(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT E'oops",
        "SELECT 'oops",
        "SELECT $$oops",
    ],
)
def test_validate_rejects_unclosed_literals(sql):
    with pytest.raises(ValueError, match="Незакрытая строка"):
        validate_adhoc_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 /* unclosed",
        "SELECT 1 /* outer /* nested */",
        "SELECT 1 /* outer /* inner */",
    ],
)
def test_validate_rejects_unclosed_block_comment(sql):
    with pytest.raises(ValueError, match="Незакрытый блочный комментарий"):
        validate_adhoc_sql(sql)


def test_validate_keeps_literal_payload():
    sql = "SELECT 'DELETE';   "
    assert validate_adhoc_sql(sql) == "SELECT 'DELETE'"


def test_strip_sql_comments_skips_literals():
    from core.sql_guard import strip_sql_comments

    text = "SELECT 'a -- b' /* c */ FROM t -- d"
    cleaned = strip_sql_comments(text)
    assert "'a -- b'" in cleaned
    assert "/* c */" not in cleaned
    assert "-- d" not in cleaned


def test_apply_max_row_limit_wraps_select():
    wrapped = apply_max_row_limit("SELECT * FROM vm_static", 2000)
    assert wrapped.startswith("SELECT * FROM (")
    assert wrapped.endswith("LIMIT 2000")


def test_apply_max_row_limit_skips_explain():
    sql = "EXPLAIN SELECT 1"
    assert apply_max_row_limit(sql, 10) == sql

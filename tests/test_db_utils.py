"""
Unit-тесты для src/core/db_utils.py.
"""
from unittest.mock import MagicMock, patch

import pytest

from core.config import STATEMENT_TIMEOUT_MS, statement_timeout_ms
from core.db_utils import (
    PG_READ_ONLY_OPTIONS,
    get_available_databases,
    get_db_params,
    get_psycopg2_connect_kwargs,
    get_sqlalchemy_engine,
    get_table_list,
    load_sql_df,
    read_sql_df,
)
from core.exceptions import DataLoadError, format_load_error, is_statement_timeout

# --- Тесты для get_db_params ---

def test_get_db_params_success(monkeypatch):
    monkeypatch.setenv("DB_HOST", "myhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_USER", "admin")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_NAME", "default_db")
    
    params = get_db_params("target_db")
    
    assert params["host"] == "myhost"
    assert params["port"] == 5433
    assert params["user"] == "admin"
    assert params["password"] == "secret"
    assert params["dbname"] == "target_db"
    assert params["options"] == PG_READ_ONLY_OPTIONS
    assert "default_transaction_read_only=on" in PG_READ_ONLY_OPTIONS
    assert f"statement_timeout={STATEMENT_TIMEOUT_MS}ms" in PG_READ_ONLY_OPTIONS

def test_get_db_params_defaults(monkeypatch):
    """Тест дефолтов. Явно удаляем переменные, чтобы перебить direnv/.env"""
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_PORT", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False) # Критично для теста
    
    params = get_db_params(None)
    
    assert params["host"] == "localhost"
    assert params["port"] == 5432
    assert params["user"] == "postgres"
    assert params["dbname"] == "postgres"
    assert params["options"] == PG_READ_ONLY_OPTIONS


def test_get_psycopg2_connect_kwargs_includes_timeout(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "secret")
    kwargs = get_psycopg2_connect_kwargs("engine")
    assert kwargs["dbname"] == "engine"
    assert kwargs["connect_timeout"] == 10
    assert kwargs["options"] == PG_READ_ONLY_OPTIONS
    assert "statement_timeout=" in kwargs["options"]


def test_get_db_params_missing_password(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="Не задан пароль для БД"):
        get_db_params("any_db")

# --- Тесты для get_table_list ---

@patch("core.db_utils.get_sqlalchemy_engine")
def test_get_table_list_success(mock_get_engine):
    mock_conn = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("table_a",), ("table_b",)]
    
    mock_conn.execute.return_value = mock_result
    mock_engine_instance = MagicMock()
    # Настройка контекстного менеджера для engine.connect()
    mock_engine_instance.connect.return_value.__enter__.return_value = mock_conn
    mock_get_engine.return_value = mock_engine_instance
    
    tables = get_table_list("test_db", "public")
    
    assert tables == ["table_a", "table_b"]
    mock_get_engine.assert_called_once_with("test_db")
    mock_conn.execute.assert_called_once()

@patch("core.db_utils.get_sqlalchemy_engine")
def test_get_table_list_error(mock_get_engine):
    mock_engine_instance = MagicMock()
    mock_engine_instance.connect.side_effect = Exception("Connection failed")
    mock_get_engine.return_value = mock_engine_instance
    
    tables = get_table_list("test_db")
    assert tables == []

# --- Тесты для get_available_databases ---

@patch("core.db_utils.psycopg2.connect")
@patch("core.db_utils.get_db_params")
def test_get_available_databases_first_try(mock_get_params, mock_connect):
    mock_get_params.return_value = {"host": "h", "port": 1, "user": "u", "password": "p", "dbname": "postgres"}
    
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [("db1",), ("db2",)]
    
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    # Настройка with psycopg2.connect(...) as conn:
    mock_connect.return_value.__enter__.return_value = mock_conn
    
    dbs = get_available_databases()
    
    assert dbs == ["db1", "db2"]
    assert mock_connect.call_count == 1

@patch("core.db_utils.psycopg2.connect")
@patch("core.db_utils.get_db_params")
def test_get_available_databases_fallback(mock_get_params, mock_connect):
    """Тест фоллбэка. Первый вызов падает, второй работает."""
    mock_get_params.return_value = {"host": "h", "port": 1, "user": "u", "password": "p", "dbname": "dummy"}
    
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [("db_from_template",)]
    
    # Создаем валидное соединение для второго вызова
    valid_conn = MagicMock()
    valid_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    # side_effect: 1-й вызов -> Exception, 2-й вызов -> valid_conn (как контекстный менеджер)
    # Важно: mock_connect должен возвращать объект, у которого есть __enter__
    # Поэтому мы возвращаем не просто valid_conn, а настраиваем его как context manager
    valid_context = MagicMock()
    valid_context.__enter__.return_value = valid_conn
    
    mock_connect.side_effect = [Exception("Fail postgres"), valid_context]
    
    dbs = get_available_databases()
    
    assert dbs == ["db_from_template"]
    assert mock_connect.call_count == 2

@patch("core.db_utils.psycopg2.connect")
@patch("core.db_utils.get_db_params")
def test_get_available_databases_all_fail(mock_get_params, mock_connect):
    mock_connect.side_effect = Exception("Total failure")
    mock_get_params.return_value = {"host": "h", "port": 1, "user": "u", "password": "p", "dbname": "dummy"}
    
    dbs = get_available_databases()
    
    assert dbs == []
    assert mock_connect.call_count == 2


def test_is_statement_timeout_by_message():
    assert is_statement_timeout(Exception("canceling statement due to statement timeout"))
    assert not is_statement_timeout(Exception("syntax error"))


class QueryCanceled(Exception):
    """Имя как у psycopg2.errors.QueryCanceled."""


def test_is_statement_timeout_by_class_and_cause():
    assert is_statement_timeout(QueryCanceled("canceled"))
    wrapped = RuntimeError("driver")
    wrapped.__cause__ = QueryCanceled("canceled")
    assert is_statement_timeout(wrapped)


def test_format_load_error_timeout():
    msg = format_load_error(Exception("statement timeout"))
    assert "таймауту" in msg
    assert str(STATEMENT_TIMEOUT_MS // 1000) in msg


def test_format_load_error_read_only():
    msg = format_load_error(Exception("cannot execute INSERT in a read-only transaction"))
    assert "только чтение" in msg


def test_statement_timeout_ms_from_env(monkeypatch):
    monkeypatch.setenv("STATEMENT_TIMEOUT_MS", "15000")
    assert statement_timeout_ms() == 15000
    monkeypatch.delenv("STATEMENT_TIMEOUT_MS")
    assert statement_timeout_ms() == 30000


@patch("core.db_utils.create_engine", side_effect=RuntimeError("pool down"))
def test_get_sqlalchemy_engine_wraps_errors(mock_create, monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "secret")
    with pytest.raises(DataLoadError, match="pool down"):
        get_sqlalchemy_engine("wrap_engine_errors")


@patch("core.db_utils.pd.read_sql")
def test_read_sql_df_wraps_errors(mock_read_sql):
    mock_read_sql.side_effect = Exception("relation missing")
    with pytest.raises(DataLoadError, match="relation missing"):
        read_sql_df(MagicMock(), "SELECT 1")


@patch("core.db_utils.get_sqlalchemy_engine")
def test_load_sql_df_engine_failure(mock_get_engine):
    mock_get_engine.side_effect = RuntimeError("pool down")
    with pytest.raises(DataLoadError, match="pool down"):
        load_sql_df("engine", "SELECT 1")

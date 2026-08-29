"""
Unit-тесты для src/core/db_utils.py.
"""
from unittest.mock import MagicMock, patch

import pytest

from core.db_utils import (
    PG_READ_ONLY_OPTIONS,
    get_available_databases,
    get_db_params,
    get_psycopg2_connect_kwargs,
    get_table_list,
)

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
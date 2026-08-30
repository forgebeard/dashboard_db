"""Юнит-тесты логики SQL-редактора без Streamlit-виджетов."""

import json
from pathlib import Path

import pandas as pd

from core.config import MAX_ROW_LIMIT
from core.sql_editor import (
    _HISTORY_LABEL_LEN,
    _LAST_RESULT_KEY,
    _SQL_INPUT_KEY,
    _WARNING_ROW_THRESHOLD,
    _history_label,
    build_last_result,
    clear_last_sql_result,
    load_history_file,
    load_history_query,
    next_history,
    save_history_file,
)


def test_next_history_inserts_front_and_dedupes():
    history = ["SELECT 1", "SELECT 2"]
    updated = next_history(history, "SELECT 2")
    assert updated[0] == "SELECT 2"
    assert updated.count("SELECT 2") == 1
    assert updated[1] == "SELECT 1"


def test_next_history_caps_size():
    history = [f"SELECT {i}" for i in range(10)]
    updated = next_history(history, "SELECT newest", max_size=10)
    assert len(updated) == 10
    assert updated[0] == "SELECT newest"
    assert "SELECT 9" not in updated


def test_next_history_strips_and_ignores_empty():
    history = ["SELECT 1"]
    assert next_history(history, "   ") == ["SELECT 1"]
    assert next_history(history, "  SELECT 2  ")[0] == "SELECT 2"


def test_load_history_query_writes_input_key():
    state: dict = {}
    load_history_query(state, "SELECT 1")
    assert state[_SQL_INPUT_KEY] == "SELECT 1"


def test_load_history_query_skips_empty():
    state = {_SQL_INPUT_KEY: "SELECT 1"}
    load_history_query(state, "")
    assert state[_SQL_INPUT_KEY] == "SELECT 1"


def test_history_label_placeholder_and_truncate():
    assert _history_label("") == "История"
    long_sql = "SELECT " + "x" * 80
    label = _history_label(long_sql)
    assert label.endswith("...")
    assert len(label) == _HISTORY_LABEL_LEN + 3


def test_clear_last_sql_result_on_db_switch():
    state = {
        _LAST_RESULT_KEY: {"df": pd.DataFrame({"a": [1]}), "row_count": 1},
        _SQL_INPUT_KEY: "SELECT 1",
    }
    clear_last_sql_result(state)
    assert _LAST_RESULT_KEY not in state
    assert state[_SQL_INPUT_KEY] == "SELECT 1"
    clear_last_sql_result(state)


def test_build_last_result_flags():
    empty = build_last_result(pd.DataFrame(), 12.3)
    assert empty["empty"] is True
    assert empty["truncated"] is False
    assert empty["large"] is False
    assert empty["row_count"] == 0
    assert empty["elapsed_ms"] == 12.3

    large_n = _WARNING_ROW_THRESHOLD + 1
    large = build_last_result(pd.DataFrame({"a": range(large_n)}), 1.0)
    assert large["large"] is True
    assert large["truncated"] is False

    capped = build_last_result(pd.DataFrame({"a": range(MAX_ROW_LIMIT)}), 2.0)
    assert capped["truncated"] is True
    assert capped["large"] is False


def test_load_history_file_missing_and_other_db(tmp_path: Path):
    path = tmp_path / "sql_history.json"
    assert load_history_file(path, "engine") == []
    save_history_file(path, "engine", ["SELECT 1", "SELECT 2"])
    assert load_history_file(path, "other") == []
    assert load_history_file(path, "engine") == ["SELECT 1", "SELECT 2"]


def test_save_history_file_keeps_other_dumps(tmp_path: Path):
    path = tmp_path / "sql_history.json"
    save_history_file(path, "a", ["SELECT a"])
    save_history_file(path, "b", ["SELECT b"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["a"] == ["SELECT a"]
    assert payload["b"] == ["SELECT b"]


def test_load_history_file_corrupt_json(tmp_path: Path):
    path = tmp_path / "sql_history.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_history_file(path, "engine") == []


def test_save_history_file_normalizes_and_caps(tmp_path: Path):
    path = tmp_path / "sql_history.json"
    queries = [f"SELECT {i}" for i in range(12)] + ["", 1]  # type: ignore[list-item]
    save_history_file(path, "engine", queries)
    loaded = load_history_file(path, "engine")
    assert len(loaded) == 10
    assert loaded[0] == "SELECT 0"

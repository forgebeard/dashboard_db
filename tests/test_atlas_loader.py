"""
Unit-тесты для src/atlas/data_loader.py.
"""
import json
from unittest.mock import patch

import pytest

# sys и Path для sys.path больше не нужны для импорта модулей проекта
import atlas.data_loader
from atlas.data_loader import load_atlas_data


@pytest.fixture
def mock_streamlit():
    """Мокирует функции Streamlit."""
    with patch("atlas.data_loader.st") as mock_st:
        mock_st.session_state = {}
        yield mock_st

@pytest.fixture
def temp_valid_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    content = {
        "group": "TestGroup",
        "tables": {
            "table_a": {"col1": "val1"},
            "table_b": {"col2": "val2"}
        }
    }
    (data_dir / "valid.json").write_text(json.dumps(content), encoding="utf-8")
    return data_dir

@pytest.fixture
def temp_duplicate_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    file1 = {"group": "G1", "tables": {"common_table": {"source": "file1"}}}
    file2 = {"group": "G2", "tables": {"common_table": {"source": "file2"}}}
    (data_dir / "aaa.json").write_text(json.dumps(file1), encoding="utf-8")
    (data_dir / "bbb.json").write_text(json.dumps(file2), encoding="utf-8")
    return data_dir

@pytest.fixture
def temp_broken_data(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "broken.json").write_text("{ invalid json", encoding="utf-8")
    (data_dir / "good.json").write_text(json.dumps({"group": "G", "tables": {"t1": {}}}), encoding="utf-8")
    return data_dir

def test_load_success(mock_streamlit, temp_valid_data, monkeypatch):
    monkeypatch.setattr(atlas.data_loader, "ATLAS_DIR", temp_valid_data)
    result = load_atlas_data()
    assert "tables" in result
    assert "table_a" in result["tables"]
    assert "table_b" in result["tables"]
    assert result["tables"]["table_a"]["group"] == "TestGroup"

def test_load_duplicates(mock_streamlit, temp_duplicate_data, monkeypatch):
    monkeypatch.setattr(atlas.data_loader, "ATLAS_DIR", temp_duplicate_data)
    result = load_atlas_data()
    assert "common_table" in result["tables"]
    assert result["tables"]["common_table"]["source"] == "file1"
    mock_streamlit.warning.assert_called()

def test_load_broken_json(mock_streamlit, temp_broken_data, monkeypatch):
    monkeypatch.setattr(atlas.data_loader, "ATLAS_DIR", temp_broken_data)
    result = load_atlas_data()
    assert "t1" in result["tables"]
    mock_streamlit.error.assert_called()

def test_load_empty_dir(mock_streamlit, tmp_path, monkeypatch):
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()
    monkeypatch.setattr(atlas.data_loader, "ATLAS_DIR", empty_dir)
    result = load_atlas_data()
    assert result == {"tables": {}}
    mock_streamlit.warning.assert_called()

def test_load_missing_dir(mock_streamlit, tmp_path, monkeypatch):
    missing_dir = tmp_path / "no_such_dir"
    monkeypatch.setattr(atlas.data_loader, "ATLAS_DIR", missing_dir)
    result = load_atlas_data()
    assert result == {"tables": {}}
    mock_streamlit.warning.assert_called()
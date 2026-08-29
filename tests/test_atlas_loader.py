"""
Unit-тесты для src/atlas/data_loader.py.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import atlas.data_loader
from atlas.data_loader import (
    apply_compat,
    field_compat_note,
    filter_groups_for_release,
    format_changelog_details,
    format_changelog_intro,
    load_atlas_data,
    load_changelog,
    load_compat,
    release_badge_text,
    release_key_from_label,
    table_visible_for_release,
    visible_fields_doc,
)


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
    (data_dir / "good.json").write_text(
        json.dumps({"group": "G", "tables": {"t1": {}}}), encoding="utf-8"
    )
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


def _compat_sample():
    return {
        "tables": {
            "old_tbl": {"until": "7.3"},
            "new_tbl": {"since": "8"},
        },
        "columns": {
            "shared.old_col": {"until": "7.3", "successor": "shared.new_col"},
            "shared.new_col": {"since": "8", "predecessor": "shared.old_col"},
        },
    }


def test_apply_compat_merges_since_until_and_columns():
    tables = {
        "old_tbl": {"fields_doc": {}},
        "new_tbl": {"fields_doc": {}},
        "shared": {
            "fields_doc": {
                "old_col": "legacy",
                "new_col": "current",
                "common": "both",
            }
        },
    }
    apply_compat(tables, _compat_sample())
    assert tables["old_tbl"]["until"] == "7.3"
    assert tables["new_tbl"]["since"] == "8"
    assert "since" not in tables["shared"]
    assert tables["shared"]["column_compat"]["old_col"]["successor"] == "shared.new_col"


def test_table_visible_for_release_matrix():
    old = {"until": "7.3"}
    new = {"since": "8"}
    common = {}
    assert table_visible_for_release(old, "7.3") is True
    assert table_visible_for_release(old, "8") is False
    assert table_visible_for_release(new, "8") is True
    assert table_visible_for_release(new, "7.3") is False
    assert table_visible_for_release(common, "8") is True
    assert table_visible_for_release(common, None) is True
    assert table_visible_for_release(old, None) is False
    assert table_visible_for_release(new, None) is False


def test_visible_fields_doc_hides_other_release_columns():
    info = {
        "fields_doc": {"old_col": "a", "new_col": "b", "common": "c"},
        "column_compat": {
            "old_col": {"until": "7.3"},
            "new_col": {"since": "8"},
        },
    }
    assert set(visible_fields_doc(info, "7.3")) == {"old_col", "common"}
    assert set(visible_fields_doc(info, "8")) == {"new_col", "common"}
    assert set(visible_fields_doc(info, None)) == {"common"}


def test_release_helpers():
    assert release_key_from_label("РЕД ВИРТ 8") == "8"
    assert release_key_from_label("РЕД ВИРТ 7.3") == "7.3"
    assert release_key_from_label(None) is None
    assert release_badge_text({"since": "8"}) == "только РЕД ВИРТ 8"
    assert release_badge_text({}) is None
    note = field_compat_note(
        {"until": "7.3", "successor": "vm_static.virtio_scsi_multi_queues"}
    )
    assert "только РЕД ВИРТ 7.3" in note
    assert "virtio_scsi_multi_queues" in note


def test_load_applies_compat_file(mock_streamlit, temp_valid_data, tmp_path, monkeypatch):
    compat_path = tmp_path / "compat.json"
    compat_path.write_text(
        json.dumps({"tables": {"table_a": {"until": "7.3"}}, "columns": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(atlas.data_loader, "ATLAS_DIR", temp_valid_data)
    monkeypatch.setattr(atlas.data_loader, "COMPAT_PATH", compat_path)
    result = load_atlas_data()
    assert result["tables"]["table_a"]["until"] == "7.3"
    assert "until" not in result["tables"]["table_b"]


def test_compat_overlay_tables_exist_in_json_catalog():
    data_dir = Path(atlas.data_loader.ATLAS_DIR)
    table_fields: dict[str, set[str]] = {}
    for path in data_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for name, meta in (payload.get("tables") or {}).items():
            table_fields[name] = set((meta.get("fields_doc") or {}).keys())
    compat = load_compat()
    assert set(compat["tables"]) <= set(table_fields)
    for qualified in compat["columns"]:
        table, _, column = qualified.partition(".")
        assert column in table_fields[table], qualified


def test_changelog_intro_and_details_from_frozen_file():
    changelog = load_changelog()
    intro = format_changelog_intro(changelog)
    details = format_changelog_details(changelog)
    assert "вместо" in intro
    assert "`sp_events`" in intro
    assert "`host_template`" in intro
    assert "обновлены 4" not in intro
    assert "virtio_scsi_multi_queues_enabled" in details
    assert "переименовано и изменён тип" in details
    assert "удалено поле" in details
    assert "добавлены поля" in details
    assert "**Поля добавлены**" not in details
    assert "добавлено поле: `virtio_scsi_multi_queues`" not in details
    assert "vds_interface_statistics` и `vm_interface_statistics" in details
    assert "изменён тип полей с int8 на numeric" in details
    assert "gluster_scheduler_job_id" in details
    assert "с varchar на uuid" in details
    listed = {
        item["name"]
        for key in ("tables_added", "tables_removed")
        for item in changelog[key]
    }
    assert "vds_static" not in listed
    assert "vm_static" not in listed


def test_format_changelog_intro_replacement_sentence():
    changelog = {
        "tables_added": [
            {"name": "new_a", "group": "Хранилище"},
            {"name": "new_b", "group": "Хранилище"},
        ],
        "tables_removed": [
            {"name": "old_a", "group": "Хранилище"},
        ],
        "renames": [],
        "columns_removed": [],
        "columns_added": [],
        "columns_type": [],
    }
    text = format_changelog_intro(changelog)
    assert "вместо `old_a` — `new_a`, `new_b`" in text


def test_format_changelog_details_one_table_add_and_remove():
    changelog = {
        "tables_added": [],
        "tables_removed": [],
        "renames": [],
        "columns_removed": [{"name": "t.gone", "type": "bool"}],
        "columns_added": [{"table": "t", "column": "fresh", "type": "int4"}],
        "columns_type": [],
    }
    text = format_changelog_details(changelog)
    assert "- В `t` удалено поле: `gone`." in text
    assert "- В `t` добавлено поле: `fresh`." in text
    assert "**Поля добавлены**" not in text


def test_compat_file_cpu_topology_and_host_template():
    compat = load_compat()
    assert table_visible_for_release(compat["tables"]["host_template"], "8") is True
    assert table_visible_for_release(compat["tables"]["host_template"], "7.3") is False
    tables = {
        "vds_dynamic": {
            "fields_doc": {"status": "s", "cpu_topology": "topo"},
        }
    }
    apply_compat(tables, compat)
    info = tables["vds_dynamic"]
    assert "cpu_topology" in visible_fields_doc(info, "8")
    assert "cpu_topology" not in visible_fields_doc(info, "7.3")
    assert "status" in visible_fields_doc(info, "7.3")


def test_filter_groups_for_release_skips_versioned_tables():
    groups = {"": {"vds_static": "core", "host_template": "tpl"}}
    only_73 = filter_groups_for_release(groups, "7.3")
    assert "host_template" not in only_73[""]
    assert "vds_static" in only_73[""]
    only_8 = filter_groups_for_release(groups, "8")
    assert "host_template" in only_8[""]
    unknown = filter_groups_for_release(groups, None)
    assert "host_template" not in unknown[""]
    assert filter_groups_for_release({"": {"host_template": "tpl"}}, "7.3") == {}


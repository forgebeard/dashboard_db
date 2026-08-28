"""
Unit-тесты для src/vms/vms_utils.py.
"""
import pandas as pd
from unittest.mock import patch, MagicMock
from vms.vms_utils import (
    fetch_vms_data,
    format_vm_layer_issues,
    process_vm_dataframe,
)
from core.constants import VM_STATUS_MAP

EXPECTED_COLS = [
    "Имя ВМ",
    "UUID",
    "Статус",
    "_status_code",
    "Слои",
    "_layer_code",
    "Хост",
    "Кластер",
    "Дата-центр",
]


def _vm_frame(**overrides):
    data = {
        "vm_guid": ["v1", "v2"],
        "vm_name": ["vm-one", "vm-two"],
        "cluster_id": ["c1", "c2"],
        "vm_status_code": [1, 0],
        "run_on_vds": ["h1", None],
        "storage_pool_id": ["dc1", "dc2"],
        "layer_issue_codes": [None, None],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_format_vm_layer_issues_order():
    assert format_vm_layer_issues(None) == ("—", None)
    assert format_vm_layer_issues("2") == ("LOCKED", 2)
    assert format_vm_layer_issues("2,3,4") == ("ILLEGAL, LOCKED, MERGING", 3)
    assert format_vm_layer_issues([4, 2]) == ("LOCKED, MERGING", 2)


def test_process_vm_dataframe_basic():
    """Тест базовой обработки: статусы, маппинг имен."""
    df = _vm_frame()
    clusters = {"c1": "Cluster-One", "c2": "Cluster-Two"}
    hosts = {"h1": "Host-One"}
    dc_map = {"dc1": "DC-One", "dc2": "DC-Two"}

    result = process_vm_dataframe(df, clusters, hosts, dc_map, show_problems=False)

    assert list(result.columns) == EXPECTED_COLS

    row1 = result.iloc[0]
    assert row1["Имя ВМ"] == "vm-one"
    assert row1["Статус"] == VM_STATUS_MAP.get(1, "Code 1")
    assert row1["Хост"] == "Host-One"
    assert row1["_status_code"] == 1
    assert row1["Слои"] == "—"

    row2 = result.iloc[1]
    assert row2["Хост"] == "—"
    assert row2["Статус"] == VM_STATUS_MAP.get(0, "Code 0")


def test_process_vm_dataframe_other_excludes_down():
    df = pd.DataFrame(
        {
            "vm_guid": ["v_ok", "v_down", "v_paused", "v_locked_layer"],
            "vm_name": ["OK_VM", "Down_VM", "Paused_VM", "Locked_VM"],
            "cluster_id": ["c1", "c1", "c1", "c1"],
            "vm_status_code": [1, 0, 4, 1],
            "run_on_vds": [None, None, None, None],
            "storage_pool_id": ["dc1", "dc1", "dc1", "dc1"],
            "layer_issue_codes": [None, None, None, "3"],
        }
    )
    clusters = {"c1": "C1"}
    hosts = {}
    dc_map = {"dc1": "DC1"}

    result_all = process_vm_dataframe(df, clusters, hosts, dc_map, show_problems=False)
    assert len(result_all) == 4

    result_prob = process_vm_dataframe(df, clusters, hosts, dc_map, show_problems=True)
    assert list(result_prob["Имя ВМ"]) == ["Paused_VM"]

    result_up = process_vm_dataframe(
        df, clusters, hosts, dc_map, health_filter="up"
    )
    assert set(result_up["Имя ВМ"]) == {"OK_VM", "Locked_VM"}
    locked = result_up[result_up["Имя ВМ"] == "Locked_VM"].iloc[0]
    assert locked["Слои"] == "ILLEGAL"
    assert locked["_layer_code"] == 3
    assert locked["Статус"] == VM_STATUS_MAP.get(1, "Code 1")


def test_process_vm_dataframe_health_filter_down():
    df = _vm_frame(vm_status_code=[1, 0], vm_name=["Up_VM", "Down_VM"])
    result = process_vm_dataframe(
        df, {"c1": "C1", "c2": "C2"}, {}, {"dc1": "DC1", "dc2": "DC2"}, health_filter="down"
    )
    assert list(result["Имя ВМ"]) == ["Down_VM"]


def test_process_vm_dataframe_empty():
    df = pd.DataFrame()
    result = process_vm_dataframe(df, {}, {}, {}, False)
    assert result.empty


@patch("vms.vms_utils.pd.read_sql")
@patch("vms.vms_utils.get_sqlalchemy_engine")
def test_fetch_vms_data_no_filters(mock_get_engine, mock_read_sql):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame({"vm_guid": ["v1"]})

    filters = ("Все ДЦ", "Все кластеры", "Все хосты", "")
    clusters, hosts, dc_map = {}, {}, {}

    df = fetch_vms_data("test_db", filters, clusters, hosts, dc_map)

    assert not df.empty
    sql_text = str(mock_read_sql.call_args[0][0])
    assert "layer_issue_codes" in sql_text
    assert "has_bad_images" not in sql_text
    assert "AND" not in sql_text.split("entity_type = 'VM'")[1].split("ORDER BY")[0]


@patch("vms.vms_utils.pd.read_sql")
@patch("vms.vms_utils.get_sqlalchemy_engine")
def test_fetch_vms_data_with_host_filter(mock_get_engine, mock_read_sql):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame()

    filters = ("Все ДЦ", "Все кластеры", "MyHost", "")
    clusters, dc_map = {}, {}
    hosts = {"h_uuid_1": "MyHost"}

    fetch_vms_data("test_db", filters, clusters, hosts, dc_map)

    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]["params"]

    assert "vd.run_on_vds = :host_id" in sql_text
    assert params["host_id"] == "h_uuid_1"


@patch("vms.vms_utils.pd.read_sql")
@patch("vms.vms_utils.get_sqlalchemy_engine")
def test_fetch_vms_data_with_search(mock_get_engine, mock_read_sql):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame()

    filters = ("Все ДЦ", "Все кластеры", "Все хосты", "search_term")
    clusters, hosts, dc_map = {}, {}, {}

    fetch_vms_data("test_db", filters, clusters, hosts, dc_map)

    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]["params"]

    assert "LOWER(vs.vm_name) LIKE LOWER(:search)" in sql_text
    assert params["search"] == "%search_term%"

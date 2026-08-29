"""Unit-тесты для src/clusters/clusters_utils.py."""

from unittest.mock import MagicMock, patch

import pandas as pd

from clusters.clusters_utils import fetch_clusters_data, process_cluster_dataframe
from core.constants import CLUSTER_STATUS_MAP, CLUSTER_STATUS_OK

EXPECTED_COLS = [
    "Имя кластера",
    "UUID",
    "Статус",
    "_status_code",
    "Хостов",
    "Дата-центр",
]


def _cluster_frame(**overrides):
    data = {
        "cluster_id": ["c1", "c2", "c3"],
        "name": ["ok-cl", "maint-cl", "bad-cl"],
        "storage_pool_id": ["dc1", "dc1", "dc2"],
        "host_count": [2, 2, 1],
        "host_up": [2, 1, 0],
        "host_maintenance": [0, 1, 0],
        "host_problems": [0, 0, 1],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_process_cluster_dataframe_basic():
    result = process_cluster_dataframe(
        _cluster_frame(), {"dc1": "DC-One", "dc2": "DC-Two"}
    )
    assert list(result.columns) == EXPECTED_COLS
    row = result.iloc[0]
    assert row["Имя кластера"] == "ok-cl"
    assert row["Статус"] == CLUSTER_STATUS_MAP[CLUSTER_STATUS_OK]
    assert row["_status_code"] == CLUSTER_STATUS_OK
    assert row["Хостов"] == 2
    assert row["Дата-центр"] == "DC-One"
    assert result.iloc[1]["Статус"] == "Ok"
    assert result.iloc[2]["Статус"] == "Проблемы"


def test_process_cluster_dataframe_health_ok():
    result = process_cluster_dataframe(
        _cluster_frame(), {"dc1": "DC-One", "dc2": "DC-Two"}, health_filter="ok"
    )
    assert list(result["Имя кластера"]) == ["ok-cl", "maint-cl"]


def test_process_cluster_dataframe_health_problems():
    result = process_cluster_dataframe(
        _cluster_frame(), {"dc1": "DC-One", "dc2": "DC-Two"}, health_filter="problems"
    )
    assert list(result["Имя кластера"]) == ["bad-cl"]


def test_process_cluster_empty_hosts_is_ok():
    df = pd.DataFrame(
        {
            "cluster_id": ["c0"],
            "name": ["empty"],
            "storage_pool_id": ["dc1"],
            "host_count": [0],
            "host_up": [0],
            "host_maintenance": [0],
            "host_problems": [0],
        }
    )
    result = process_cluster_dataframe(df, {"dc1": "DC-One"})
    assert result.iloc[0]["Статус"] == "Ok"
    assert result.iloc[0]["_status_code"] == CLUSTER_STATUS_OK


def test_process_cluster_dataframe_empty():
    assert process_cluster_dataframe(pd.DataFrame(), {}).empty


@patch("clusters.clusters_utils.read_sql_df")
@patch("clusters.clusters_utils.get_sqlalchemy_engine")
def test_fetch_clusters_data_no_filters(mock_get_engine, mock_read_sql):
    mock_get_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame({"cluster_id": ["c1"]})
    df = fetch_clusters_data("test_db", ("Все ДЦ", ""), {})
    assert not df.empty
    sql = str(mock_read_sql.call_args[0][1])
    assert "host_problems" in sql
    assert "FILTER" in sql
    assert mock_read_sql.call_args.kwargs.get("params") in (None, {})


@patch("clusters.clusters_utils.read_sql_df")
@patch("clusters.clusters_utils.get_sqlalchemy_engine")
def test_fetch_clusters_data_dc_and_search(mock_get_engine, mock_read_sql):
    mock_get_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()
    fetch_clusters_data(
        "test_db",
        ("Main DC", "prod"),
        {"dc-1": "Main DC"},
    )
    params = mock_read_sql.call_args.kwargs["params"]
    assert params["dc_id"] == "dc-1"
    assert params["search"] == "%prod%"

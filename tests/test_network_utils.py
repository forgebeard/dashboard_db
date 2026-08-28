"""Unit-тесты для src/networks/network_utils.py."""

from unittest.mock import MagicMock, patch

import pandas as pd

from networks.network_utils import fetch_networks_data, process_networks_dataframe


def test_process_empty():
    assert process_networks_dataframe(pd.DataFrame(), {}).empty


def test_process_columns_and_vlan():
    df = pd.DataFrame(
        {
            "id": ["n1"],
            "name": ["ovirtmgmt"],
            "vlan_id": [15],
            "vm_network": [True],
            "mtu": [1500],
            "storage_pool_id": ["dc1"],
        }
    )
    result = process_networks_dataframe(df, {"dc1": "DC_PROD"})
    assert list(result.columns) == [
        "Имя сети",
        "UUID",
        "VLAN",
        "VM Network",
        "MTU",
        "Дата-центр",
    ]
    assert result.iloc[0]["VLAN"] == "VLAN 15"
    assert result.iloc[0]["Дата-центр"] == "DC_PROD"
    assert result.iloc[0]["UUID"] == "n1"


@patch("networks.network_utils.pd.read_sql")
@patch("networks.network_utils.get_sqlalchemy_engine")
def test_fetch_dc_and_search(mock_engine, mock_read_sql):
    mock_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()
    fetch_networks_data("db", ("MyDC", "mgmt"), {"dc-uuid": "MyDC"})
    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]["params"]
    assert "n.storage_pool_id = :dc_id" in sql_text
    assert params["dc_id"] == "dc-uuid"
    assert params["search"] == "%mgmt%"

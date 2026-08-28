"""Unit-тесты для src/disks/disks_utils.py."""

from unittest.mock import MagicMock, patch

import pandas as pd

from disks.disks_utils import fetch_disks_data, process_disks_dataframe

GIB = 1024**3


def _raw(**kwargs):
    row = {
        "disk_alias": "os",
        "image_guid": "img-1",
        "imagestatus": 1,
        "size": 40 * GIB,
        "actual_size": 10 * GIB,
        "active": True,
        "vm_name": "vm-a",
        "storage_name": "data1",
    }
    row.update(kwargs)
    return row


def test_process_empty():
    assert process_disks_dataframe(pd.DataFrame()).empty


def test_unknown_status_and_columns():
    result = process_disks_dataframe(pd.DataFrame([_raw(imagestatus=9)]))
    assert result.iloc[0]["Статус"] == "Code 9"
    assert "_status_code" in result.columns
    assert result.iloc[0]["_status_code"] == 9


def test_health_filter():
    df = pd.DataFrame(
        [_raw(image_guid="ok", imagestatus=1), _raw(image_guid="bad", imagestatus=3)]
    )
    ok = process_disks_dataframe(df, health_filter="ok")
    assert list(ok["UUID образа"]) == ["ok"]
    problems = process_disks_dataframe(df, health_filter="problems")
    assert list(problems["UUID образа"]) == ["bad"]
    assert problems.iloc[0]["Статус"] == "ILLEGAL"


@patch("disks.disks_utils.pd.read_sql")
@patch("disks.disks_utils.get_sqlalchemy_engine")
def test_fetch_no_status_in_sql(mock_engine, mock_read_sql):
    mock_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()
    fetch_disks_data("db", ("", "", ""))
    sql_text = str(mock_read_sql.call_args[0][0])
    assert "imagestatus IN" not in sql_text
    assert "LIMIT 500" in sql_text


@patch("disks.disks_utils.pd.read_sql")
@patch("disks.disks_utils.get_sqlalchemy_engine")
def test_fetch_search_no_limit(mock_engine, mock_read_sql):
    mock_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()
    fetch_disks_data("db", ("os", "", ""))
    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]["params"]
    assert "LIMIT 500" not in sql_text
    assert params["search_disk"] == "%os%"

"""Unit-тесты для src/disks/disks_utils.py."""

from unittest.mock import MagicMock, patch

import pandas as pd

from disks.disks_utils import fetch_disks_data, process_disks_dataframe

GIB = 1024**3


def _raw(**kwargs):
    row = {
        "disk_id": "disk-1",
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
    assert result.iloc[0]["UUID диска"] == "disk-1"
    assert "_status_code" in result.columns
    assert result.iloc[0]["_status_code"] == 9


def test_health_filter():
    df = pd.DataFrame(
        [
            _raw(disk_id="ok-disk", image_guid="ok", imagestatus=1),
            _raw(disk_id="bad-disk", image_guid="bad", imagestatus=3),
        ]
    )
    ok = process_disks_dataframe(df, health_filter="ok")
    assert list(ok["UUID диска"]) == ["ok-disk"]
    problems = process_disks_dataframe(df, health_filter="problems")
    assert list(problems["UUID диска"]) == ["bad-disk"]
    assert problems.iloc[0]["Статус"] == "ILLEGAL"


def test_two_layers_one_disk_worst_status():
    df = pd.DataFrame(
        [
            _raw(
                image_guid="img-ok",
                imagestatus=1,
                active=True,
                size=40 * GIB,
                actual_size=10 * GIB,
            ),
            _raw(
                image_guid="img-merge",
                imagestatus=4,
                active=False,
                size=40 * GIB,
                actual_size=5 * GIB,
            ),
        ]
    )
    result = process_disks_dataframe(df)
    assert len(result) == 1
    assert result.iloc[0]["Статус"] == "MERGING"
    assert result.iloc[0]["_inspect_image_guid"] == "img-merge"
    assert result.iloc[0]["Факт. размер"] == "15.00 ГБ"
    problems = process_disks_dataframe(df, health_filter="problems")
    assert list(problems["UUID диска"]) == ["disk-1"]


@patch("disks.disks_utils.pd.read_sql")
@patch("disks.disks_utils.get_sqlalchemy_engine")
def test_fetch_no_status_in_sql(mock_engine, mock_read_sql):
    mock_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()
    fetch_disks_data("db", ("", "", ""))
    sql_text = str(mock_read_sql.call_args[0][0])
    sql_l = sql_text.lower()
    assert "imagestatus IN" not in sql_text
    assert "limit 500" in sql_l
    assert "max(creation_date)" in sql_l
    assert "newest.image_group_id" in sql_l
    assert sql_l.count("limit 500") == 1
    after_outer_group = sql_l.rsplit("group by", 1)[-1]
    assert "limit 500" not in after_outer_group


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


@patch("disks.disks_utils.pd.read_sql")
@patch("disks.disks_utils.get_sqlalchemy_engine")
def test_fetch_one_row_per_image(mock_engine, mock_read_sql):
    mock_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()
    fetch_disks_data("db", ("", "", ""))
    sql = " ".join(str(mock_read_sql.call_args[0][0]).lower().split())
    assert "string_agg(distinct vm.vm_name" in sql
    assert "string_agg(distinct sd.storage_name" in sql
    assert "group by" in sql
    assert "vd.type = 'disk'" in sql
    assert "disk_id" in sql

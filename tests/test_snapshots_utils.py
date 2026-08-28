"""Unit-тесты для src/snapshots/snapshots_utils.py."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from snapshots.snapshots_utils import fetch_snapshots_data, process_snapshot_dataframe

GIB = 1024**3


def _row(**kwargs):
    base = {
        "snapshot_id": "snap-a",
        "_vm_id": "vm-1",
        "vm_name": "tsk1-ts15_1",
        "creation_date": datetime(2026, 3, 14, 12, 2),
        "snapshot_type": "REGULAR",
        "image_guid": "img-a",
        "size": GIB,
        "_image_status_code": 1,
        "storage_name": "data01",
    }
    base.update(kwargs)
    return base


def test_process_empty_dataframe():
    assert process_snapshot_dataframe(pd.DataFrame()).empty


def test_two_images_same_snapshot_collapse():
    df = pd.DataFrame(
        [
            _row(image_guid="img-1", size=10 * GIB),
            _row(image_guid="img-2", size=5 * GIB, storage_name="data02"),
        ]
    )
    result = process_snapshot_dataframe(df)
    assert len(result) == 1
    assert result.iloc[0]["Размер"] == 15.0
    assert result.iloc[0]["Хранилище"] == "data01, data02"
    assert result.iloc[0]["Статус"] == "OK"
    assert result.iloc[0]["UUID снапшота"] == "snap-a"


def test_vm_name_repeated_per_snapshot():
    df = pd.DataFrame(
        [
            _row(snapshot_id="snap-1", image_guid="img-1", snapshot_type="REGULAR"),
            _row(
                snapshot_id="snap-2",
                image_guid="img-2",
                snapshot_type="ACTIVE",
                creation_date=datetime(2026, 3, 15, 10, 0),
            ),
            _row(
                snapshot_id="snap-p",
                _vm_id="vm-2",
                vm_name="tsk1-perco01",
                image_guid="img-p",
                snapshot_type="ACTIVE",
            ),
        ]
    )
    result = process_snapshot_dataframe(df)
    ts_rows = result[result["_vm_id"] == "vm-1"]
    assert list(ts_rows["Имя ВМ"]) == ["tsk1-ts15_1", "tsk1-ts15_1"]
    assert list(ts_rows["UUID снапшота"]) == ["snap-1", "snap-2"]
    assert "tsk1-perco01" in list(result["Имя ВМ"])


def test_display_columns_and_types():
    df = pd.DataFrame(
        [
            _row(snapshot_id="snap-1", snapshot_type="REGULAR"),
            _row(
                snapshot_id="snap-2",
                image_guid="img-2",
                snapshot_type="ACTIVE",
                creation_date=datetime(2026, 3, 15, 10, 0),
            ),
        ]
    )
    result = process_snapshot_dataframe(df)
    assert list(result.columns) == [
        "Имя ВМ",
        "UUID снапшота",
        "Дата создания",
        "Тип",
        "Статус",
        "_status_code",
        "Размер",
        "Хранилище",
        "_vm_id",
    ]
    assert list(result["Тип"]) == ["REGULAR", "ACTIVE"]
    assert "Снапшот" not in result.columns


def test_health_filter_ok_and_problems():
    df = pd.DataFrame(
        [
            _row(snapshot_id="ok-snap", _image_status_code=1),
            _row(
                snapshot_id="bad-snap",
                image_guid="img-bad",
                _image_status_code=3,
            ),
        ]
    )
    ok = process_snapshot_dataframe(df, health_filter="ok")
    assert list(ok["UUID снапшота"]) == ["ok-snap"]

    problems = process_snapshot_dataframe(df, health_filter="problems")
    assert list(problems["UUID снапшота"]) == ["bad-snap"]
    assert problems.iloc[0]["Статус"] == "ILLEGAL"


def test_unknown_image_status_code():
    df = pd.DataFrame([_row(_image_status_code=9)])
    result = process_snapshot_dataframe(df)
    assert result.iloc[0]["Статус"] == "Code 9"


def test_worst_status_prefers_illegal():
    df = pd.DataFrame(
        [
            _row(image_guid="img-ok", _image_status_code=1),
            _row(image_guid="img-lock", _image_status_code=2),
            _row(image_guid="img-ill", _image_status_code=3),
        ]
    )
    result = process_snapshot_dataframe(df)
    assert result.iloc[0]["Статус"] == "ILLEGAL"
    assert result.iloc[0]["_status_code"] == 3


@patch("snapshots.snapshots_utils.pd.read_sql")
@patch("snapshots.snapshots_utils.get_sqlalchemy_engine")
def test_fetch_sql_no_status_filter(mock_engine, mock_read_sql):
    mock_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()

    fetch_snapshots_data("test_db", ("Все ДЦ", "Все кластеры", ""), {}, {})

    sql_text = str(mock_read_sql.call_args[0][0])
    assert "vm_snapshot_id" in sql_text
    assert "s.snapshot_id" in sql_text
    assert "imagestatus IN" not in sql_text


@patch("snapshots.snapshots_utils.pd.read_sql")
@patch("snapshots.snapshots_utils.get_sqlalchemy_engine")
def test_fetch_dc_cluster_search(mock_engine, mock_read_sql):
    mock_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()

    fetch_snapshots_data(
        "test_db",
        ("MyDC", "Cluster-One", "tsk1"),
        {"dc1": "MyDC"},
        {"c1": "Cluster-One"},
    )
    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]["params"]
    assert "c.storage_pool_id = :dc_id" in sql_text
    assert "v.cluster_id = :cluster_id" in sql_text
    assert params["dc_id"] == "dc1"
    assert params["cluster_id"] == "c1"
    assert params["search"] == "%tsk1%"

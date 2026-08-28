"""Unit-тесты для src/gluster/gluster_utils.py."""

import pandas as pd

from gluster.gluster_utils import process_gluster_dataframe


def test_process_empty():
    assert process_gluster_dataframe(pd.DataFrame()).empty


def test_process_columns_no_status_type():
    df = pd.DataFrame(
        {
            "vol_name": ["gv0"],
            "_volume_id": ["vol-1"],
            "cluster_name": ["Gluster"],
            "vol_type": ["Replicate"],
            "status": ["Started"],
            "total_space": [1000],
            "used_space": [250],
            "free_space": [750],
        }
    )
    result = process_gluster_dataframe(df)
    assert list(result.columns) == [
        "Имя тома",
        "UUID",
        "Кластер",
        "Тип",
        "Статус",
        "Заполнен (%)",
    ]
    assert "_status_type" not in result.columns
    assert result.iloc[0]["Заполнен (%)"] == 25.0
    assert result.iloc[0]["Статус"] == "Started"


def test_usage_unknown_when_total_missing():
    df = pd.DataFrame(
        {
            "vol_name": ["gv0"],
            "_volume_id": ["vol-1"],
            "cluster_name": ["Gluster"],
            "vol_type": ["Replicate"],
            "status": ["Started"],
            "total_space": [None],
            "used_space": [250],
            "free_space": [None],
        }
    )
    result = process_gluster_dataframe(df)
    assert pd.isna(result.iloc[0]["Заполнен (%)"])
    assert result.iloc[0]["Заполнен (%)"] != 0.0

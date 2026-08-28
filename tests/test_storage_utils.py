"""Unit-тесты для src/storage/storage_utils.py."""

from unittest.mock import MagicMock, patch

import pandas as pd

from storage.storage_utils import fetch_storage_data, process_storage_dataframe


def _raw_storage_df():
    return pd.DataFrame({
        "storage_name": ["data_domain_1", "iso_domain", "broken_domain", "mixed_domain"],
        "sd_id": ["uuid-1", "uuid-2", "uuid-3", "uuid-4"],
        "storage_domain_type": [1, 2, 0, 1],
        "storage_type": [1, 3, 2, 2],
        "shared_status_code": [1, 0, 2, 3],
        "dc_name": ["DC_PROD", None, "DC_BROKEN", "DC_A, DC_B"],
        "available_disk_size": [200, 500, 100, 50],
        "used_disk_size": [800, 100, 200, 50],
    })


def test_process_empty_dataframe():
    result = process_storage_dataframe(pd.DataFrame())
    assert result.empty


def test_process_volume_used_plus_available():
    result = process_storage_dataframe(_raw_storage_df())
    expected_cols = [
        "Имя домена",
        "UUID",
        "Тип домена",
        "Тип хранилища",
        "Статус",
        "_status_code",
        "Дата-центр",
        "Заполнено (%)",
        "Всего (ГБ)",
        "Свободно (ГБ)",
    ]
    assert list(result.columns) == expected_cols

    row0 = result.iloc[0]
    assert row0["Тип домена"] == "Data"
    assert row0["Тип хранилища"] == "NFS"
    assert row0["Статус"] == "Active"
    assert row0["_status_code"] == 1
    assert row0["Заполнено (%)"] == 80.0
    assert row0["Всего (ГБ)"] == 1000.0
    assert row0["Свободно (ГБ)"] == 200.0

    row2 = result.iloc[2]
    assert row2["Статус"] == "Inactive"
    assert row2["Заполнено (%)"] == round(200 / 300 * 100, 1)
    assert row2["Всего (ГБ)"] == 300.0
    assert row2["Свободно (ГБ)"] == 100.0
    assert result.iloc[1]["Дата-центр"] == "—"
    assert result.iloc[1]["Статус"] == "Unattached"
    assert result.iloc[3]["Статус"] == "Mixed"


def test_zero_total_size_handling():
    df = pd.DataFrame({
        "storage_name": ["zero_sd"],
        "sd_id": ["u1"],
        "storage_domain_type": [1],
        "storage_type": [1],
        "shared_status_code": [1],
        "dc_name": ["DC"],
        "available_disk_size": [0],
        "used_disk_size": [0],
    })
    result = process_storage_dataframe(df)
    assert result.iloc[0]["Заполнено (%)"] == 0.0
    assert pd.notna(result.iloc[0]["Заполнено (%)"])
    assert result.iloc[0]["Всего (ГБ)"] == 0.0


def test_non_numeric_size_coercion():
    df = pd.DataFrame({
        "storage_name": ["bad_sd"],
        "sd_id": ["u1"],
        "storage_domain_type": [1],
        "storage_type": [1],
        "shared_status_code": [1],
        "dc_name": ["DC"],
        "available_disk_size": ["not_a_number"],
        "used_disk_size": [None],
    })
    result = process_storage_dataframe(df)
    assert result.iloc[0]["Всего (ГБ)"] == 0.0
    assert result.iloc[0]["Заполнено (%)"] == 0.0


def test_health_filter_active_and_problems():
    df = _raw_storage_df()
    active = process_storage_dataframe(df, health_filter="active")
    assert list(active["Имя домена"]) == ["data_domain_1"]

    problems = process_storage_dataframe(df, health_filter="problems")
    assert list(problems["Имя домена"]) == [
        "iso_domain",
        "broken_domain",
        "mixed_domain",
    ]


def test_engine_storage_type_and_shared_status_codes():
    from core.constants import SHARED_STATUS_MAP, STORAGE_DOMAIN_TYPE_MAP, STORAGE_TYPE_MAP

    assert STORAGE_TYPE_MAP[2] == "FCP"
    assert STORAGE_TYPE_MAP[3] == "iSCSI"
    assert STORAGE_TYPE_MAP[8] == "Glance"
    assert STORAGE_DOMAIN_TYPE_MAP[0] == "Master"
    assert STORAGE_DOMAIN_TYPE_MAP[1] == "Data"
    assert STORAGE_DOMAIN_TYPE_MAP[4] == "Image"
    assert SHARED_STATUS_MAP[0] == "Unattached"
    assert SHARED_STATUS_MAP[1] == "Active"
    assert SHARED_STATUS_MAP[2] == "Inactive"
    assert SHARED_STATUS_MAP[3] == "Mixed"

    df = pd.DataFrame({
        "storage_name": ["hosted_storage", "Dat1", "ovirt-image-repository"],
        "sd_id": ["u1", "u2", "u3"],
        "storage_domain_type": [0, 1, 4],
        "storage_type": [2, 2, 8],
        "shared_status_code": [1, 1, 1],
        "dc_name": ["DC", "DC", "DC"],
        "available_disk_size": [10, 10, 10],
        "used_disk_size": [1, 1, 1],
    })
    result = process_storage_dataframe(df)
    assert list(result["Тип хранилища"]) == ["FCP", "FCP", "Glance"]
    assert list(result["Тип домена"]) == ["Master", "Data", "Image"]


@patch("storage.storage_utils.pd.read_sql")
@patch("storage.storage_utils.get_sqlalchemy_engine")
def test_fetch_storage_data_sql_shape(mock_get_engine, mock_read_sql):
    mock_get_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()

    fetch_storage_data("test_db", ("Все ДЦ", ""), {})

    sql_text = str(mock_read_sql.call_args[0][0])
    assert "used_disk_size" in sql_text
    assert "available_disk_size" in sql_text
    assert "used_disk_size /" not in sql_text.replace(" ", "")
    assert "NULLIF" not in sql_text
    assert "storage_pool_iso_map" in sql_text
    assert "storage_pool_with_storage_domain" not in sql_text
    assert "string_agg" in sql_text
    assert "GROUP BY" in sql_text
    assert "WHERE" not in sql_text


@patch("storage.storage_utils.pd.read_sql")
@patch("storage.storage_utils.get_sqlalchemy_engine")
def test_fetch_storage_data_dc_and_search(mock_get_engine, mock_read_sql):
    mock_get_engine.return_value = MagicMock()
    mock_read_sql.return_value = pd.DataFrame()

    fetch_storage_data(
        "test_db",
        ("MyDC", "data1"),
        {"dc_uuid_1": "MyDC"},
    )

    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]["params"]
    assert "sp.id = :dc_id" in sql_text
    assert "storage_pool_iso_map" in sql_text
    assert params["dc_id"] == "dc_uuid_1"
    assert params["search"] == "%data1%"
    assert "LIKE" in sql_text.upper()

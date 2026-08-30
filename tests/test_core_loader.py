"""
Unit-тесты для src/core/data_loader.py.
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.exceptions import DataLoadError

# sys.path.append удален

@pytest.fixture(autouse=True)
def mock_streamlit_cache(monkeypatch):
    import streamlit as st
    def mock_cache_decorator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    monkeypatch.setattr(st, "cache_data", mock_cache_decorator)

@pytest.fixture
def mock_db_dependencies(monkeypatch):
    mock_engine = MagicMock(name="Engine")
    mock_get_engine = MagicMock(return_value=mock_engine)
    mock_read_sql = MagicMock()
    
    monkeypatch.setattr("core.data_loader.get_sqlalchemy_engine", mock_get_engine)
    monkeypatch.setattr("core.data_loader.read_sql_df", mock_read_sql)
    
    return {
        "engine": mock_engine,
        "get_engine": mock_get_engine,
        "read_sql": mock_read_sql
    }

def test_safe_load_dict_success(mock_db_dependencies):
    from core.data_loader import _safe_load_dict
    df = pd.DataFrame({'id_col': ['1', '2', '3'], 'name_col': ['Name1', 'Name2', 'Name3']})
    mock_db_dependencies["read_sql"].return_value = df
    result = _safe_load_dict(mock_db_dependencies["engine"], "SELECT ...", 'id_col', 'name_col')
    assert result == {'1': 'Name1', '2': 'Name2', '3': 'Name3'}
    mock_db_dependencies["read_sql"].assert_called_once()

def test_safe_load_dict_empty_df(mock_db_dependencies):
    from core.data_loader import _safe_load_dict
    mock_db_dependencies["read_sql"].return_value = pd.DataFrame()
    result = _safe_load_dict(mock_db_dependencies["engine"], "SELECT ...", 'id', 'name')
    assert result == {}

def test_safe_load_dict_null_ids(mock_db_dependencies):
    from core.data_loader import _safe_load_dict
    df = pd.DataFrame({'id_col': ['1', None, '3'], 'name_col': ['Name1', 'NameNull', 'Name3']})
    mock_db_dependencies["read_sql"].return_value = df
    result = _safe_load_dict(mock_db_dependencies["engine"], "SELECT ...", 'id_col', 'name_col')
    assert result == {'1': 'Name1', '3': 'Name3'}
    assert None not in result

def test_safe_load_dict_exception(mock_db_dependencies):
    from core.data_loader import _safe_load_dict
    mock_db_dependencies["read_sql"].side_effect = DataLoadError("DB Connection Error")
    result = _safe_load_dict(mock_db_dependencies["engine"], "SELECT ...", 'id', 'name')
    assert result == {}

def test_load_cluster_metadata_structure(mock_db_dependencies):
    from core.data_loader import load_cluster_metadata
    dfs = [
        pd.DataFrame({'cluster_id': ['c1'], 'name': ['Cluster1']}),
        pd.DataFrame({'id': ['sd1'], 'storage_name': ['SD1']}),
        pd.DataFrame({'vds_id': ['h1'], 'vds_name': ['Host1']}),
        pd.DataFrame({'id': ['dc1'], 'name': ['DC1']}),
        pd.DataFrame({'spid': ['dc1'], 'cid': ['c1']}),
        pd.DataFrame({'cid': ['c1'], 'vid': ['h1']}),
        pd.DataFrame({'table_name': ['host_template']}),
        pd.DataFrame({'version': ['04041510']}),
        pd.DataFrame(
            {
                'option_name': ['RPMVersion'],
                'option_value': ['7.3.3'],
                'version': ['general'],
            }
        ),
    ]
    mock_db_dependencies["read_sql"].side_effect = dfs
    result = load_cluster_metadata("test_db")
    
    assert 'clusters' in result
    assert 'hosts' in result
    assert result['clusters'] == {'c1': 'Cluster1'}
    assert result['hosts'] == {'h1': 'Host1'}
    assert result["engine_release"] == "РЕД ВИРТ 8"
    assert result["schema_version"] == "04041510"
    assert result["product_version"] == "7.3.3"
    mock_db_dependencies["engine"].dispose.assert_not_called()

def test_load_cluster_metadata_empty_db(mock_db_dependencies):
    from core.data_loader import load_cluster_metadata
    mock_db_dependencies["read_sql"].return_value = pd.DataFrame()
    result = load_cluster_metadata("empty_db")
    assert result['clusters'] == {}
    assert result['hosts'] == {}
    assert result["engine_release"] is None
    assert result["schema_version"] is None
    assert result["product_version"] is None
    mock_db_dependencies["engine"].dispose.assert_not_called()


def test_build_infra_filter_maps_from_cluster_meta():
    from core.data_loader import build_infra_filter_maps

    maps = build_infra_filter_maps(
        {
            "datacenters": {"dc-1": "DC_PROD"},
            "clusters": {"cl-1": "Cluster_A"},
            "hosts": {"h-1": "Host_A"},
            "dc_to_clusters": {"dc-1": ["cl-1"]},
            "cluster_to_hosts": {"cl-1": ["h-1"]},
        }
    )
    assert maps["dc_id_to_name"] == {"dc-1": "DC_PROD"}
    assert maps["cluster_to_hosts"] == {"cl-1": ["h-1"]}
    assert maps["host_to_vms"] == {}
    assert maps["vm_id_to_name"] == {}


def test_host_ids_for_infra_filters():
    from core.data_loader import host_ids_for_infra_filters

    maps = {
        "dc_id_to_name": {"dc-1": "DC_PROD", "dc-empty": "DC_EMPTY"},
        "cluster_id_to_name": {"cl-1": "Cluster_A", "cl-empty": "Cluster_Empty"},
        "host_id_to_name": {"h-1": "Host_A", "h-2": "Host_B"},
        "dc_to_clusters": {"dc-1": ["cl-1"], "dc-empty": ["cl-empty"]},
        "cluster_to_hosts": {"cl-1": ["h-1", "h-2"], "cl-empty": []},
    }

    assert host_ids_for_infra_filters(maps, "Все ДЦ", "Все кластеры", "Все хосты") is None
    assert host_ids_for_infra_filters(maps, "DC_PROD", "Все кластеры", "Все хосты") == [
        "h-1",
        "h-2",
    ]
    assert host_ids_for_infra_filters(maps, "DC_PROD", "Cluster_A", "Все хосты") == [
        "h-1",
        "h-2",
    ]
    assert host_ids_for_infra_filters(maps, "DC_PROD", "Cluster_A", "Host_B") == ["h-2"]
    assert host_ids_for_infra_filters(maps, "DC_EMPTY", "Все кластеры", "Все хосты") == []
    assert host_ids_for_infra_filters(maps, "Все ДЦ", "Cluster_Empty", "Все хосты") == []


def test_detect_engine_release_8(mock_db_dependencies):
    from core.data_loader import detect_engine_release

    mock_db_dependencies["read_sql"].return_value = pd.DataFrame(
        {"table_name": ["host_template", "infrastructure_backups"]}
    )
    assert detect_engine_release(mock_db_dependencies["engine"]) == "РЕД ВИРТ 8"


def test_detect_engine_release_73(mock_db_dependencies):
    from core.data_loader import detect_engine_release

    mock_db_dependencies["read_sql"].return_value = pd.DataFrame(
        {"table_name": ["infrastructure_backup"]}
    )
    assert detect_engine_release(mock_db_dependencies["engine"]) == "РЕД ВИРТ 7.3"


def test_detect_engine_release_unknown(mock_db_dependencies):
    from core.data_loader import detect_engine_release

    mock_db_dependencies["read_sql"].return_value = pd.DataFrame()
    assert detect_engine_release(mock_db_dependencies["engine"]) is None
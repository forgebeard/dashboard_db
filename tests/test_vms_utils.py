"""
Unit-тесты для src/vms/vms_utils.py.
"""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from vms.vms_utils import process_vm_dataframe, fetch_vms_data
from core.constants import VM_STATUS_MAP

# --- Тесты для process_vm_dataframe ---

def test_process_vm_dataframe_basic():
    """Тест базовой обработки: статусы, маппинг имен."""
    df = pd.DataFrame({
        'vm_guid': ['v1', 'v2'],
        'vm_name': ['vm-one', 'vm-two'],
        'cluster_id': ['c1', 'c2'],
        'vm_status_code': [1, 0],  # 1=Up, 0=Down
        'run_on_vds': ['h1', None], # h1 существует, None -> '—'
        'storage_pool_id': ['dc1', 'dc2'],
        'has_bad_images': [False, False]
    })
    
    clusters = {'c1': 'Cluster-One', 'c2': 'Cluster-Two'}
    hosts = {'h1': 'Host-One'}
    dc_map = {'dc1': 'DC-One', 'dc2': 'DC-Two'}
    
    result = process_vm_dataframe(df, clusters, hosts, dc_map, show_problems=False)
    
    # Проверка колонок
    expected_cols = ['Имя ВМ', 'UUID', 'Статус', '_status_code', 'Хост', 'Кластер', 'Дата-центр']
    assert list(result.columns) == expected_cols
    
    row1 = result.iloc[0]
    assert row1['Имя ВМ'] == 'vm-one'
    assert row1['Статус'] == VM_STATUS_MAP.get(1, 'Code 1')
    assert row1['Хост'] == 'Host-One'
    assert row1['_status_code'] == 1
    
    row2 = result.iloc[1]
    assert row2['Хост'] == '—' # None должен стать прочерком
    assert row2['Статус'] == VM_STATUS_MAP.get(0, 'Code 0')

def test_process_vm_dataframe_logic_problems():
    """Тест логики выявления проблемных ВМ."""
    df = pd.DataFrame({
        'vm_guid': ['v_ok', 'v_down', 'v_locked'],
        'vm_name': ['OK_VM', 'Down_VM', 'Locked_VM'],
        'cluster_id': ['c1', 'c1', 'c1'],
        'vm_status_code': [1, 0, 1], # Up, Down, Up
        'run_on_vds': [None, None, None],
        'storage_pool_id': ['dc1', 'dc1', 'dc1'],
        'has_bad_images': [False, False, True] # У третьей битый образ
    })
    
    clusters = {'c1': 'C1'}
    hosts = {}
    dc_map = {'dc1': 'DC1'}
    
    # Без фильтра
    result_all = process_vm_dataframe(df, clusters, hosts, dc_map, show_problems=False)
    assert len(result_all) == 3
    
    # С фильтром проблем
    result_prob = process_vm_dataframe(df, clusters, hosts, dc_map, show_problems=True)
    
    # Должны остаться Down_VM и Locked_VM
    assert len(result_prob) == 2
    assert 'OK_VM' not in result_prob['Имя ВМ'].values
    assert 'Down_VM' in result_prob['Имя ВМ'].values
    assert 'Locked_VM' in result_prob['Имя ВМ'].values


def test_process_vm_dataframe_health_filter_paused():
    df = pd.DataFrame({
        'vm_guid': ['v1', 'v2'],
        'vm_name': ['Up_VM', 'Paused_VM'],
        'cluster_id': ['c1', 'c1'],
        'vm_status_code': [1, 4],
        'run_on_vds': [None, None],
        'storage_pool_id': ['dc1', 'dc1'],
        'has_bad_images': [False, False],
    })
    result = process_vm_dataframe(
        df, {'c1': 'C1'}, {}, {'dc1': 'DC1'}, health_filter="paused"
    )
    assert list(result['Имя ВМ']) == ['Paused_VM']

def test_process_vm_dataframe_empty():
    df = pd.DataFrame()
    result = process_vm_dataframe(df, {}, {}, {}, False)
    assert result.empty

# --- Тесты для fetch_vms_data ---

@patch("vms.vms_utils.pd.read_sql")
@patch("vms.vms_utils.get_sqlalchemy_engine")
def test_fetch_vms_data_no_filters(mock_get_engine, mock_read_sql):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame({'vm_guid': ['v1']})
    
    filters = ('Все ДЦ', 'Все кластеры', 'Все хосты', '')
    clusters, hosts, dc_map = {}, {}, {}
    
    df = fetch_vms_data("test_db", filters, clusters, hosts, dc_map)
    
    assert not df.empty
    sql_text = str(mock_read_sql.call_args[0][0])
    # Базовый WHERE уже есть (entity_type = 'VM'), дополнительные условия через AND
    assert "AND" not in sql_text.split("WHERE")[-1].split("ORDER")[0].strip() or "AND" not in sql_text 
    # Точнее: если conditions пуст, то " AND " не добавляется.
    # В коде: if conditions: base_sql += " AND " ...
    # Значит после WHERE entity_type... сразу ORDER BY
    assert "AND" not in sql_text.split("entity_type = 'VM'")[1].split("ORDER BY")[0]

@patch("vms.vms_utils.pd.read_sql")
@patch("vms.vms_utils.get_sqlalchemy_engine")
def test_fetch_vms_data_with_host_filter(mock_get_engine, mock_read_sql):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame()
    
    filters = ('Все ДЦ', 'Все кластеры', 'MyHost', '')
    clusters, dc_map = {}, {}
    hosts = {'h_uuid_1': 'MyHost'}
    
    fetch_vms_data("test_db", filters, clusters, hosts, dc_map)
    
    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]['params']
    
    assert "vd.run_on_vds = :host_id" in sql_text
    assert params['host_id'] == 'h_uuid_1'

@patch("vms.vms_utils.pd.read_sql")
@patch("vms.vms_utils.get_sqlalchemy_engine")
def test_fetch_vms_data_with_search(mock_get_engine, mock_read_sql):
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame()
    
    filters = ('Все ДЦ', 'Все кластеры', 'Все хосты', 'search_term')
    clusters, hosts, dc_map = {}, {}, {}
    
    fetch_vms_data("test_db", filters, clusters, hosts, dc_map)
    
    sql_text = str(mock_read_sql.call_args[0][0])
    params = mock_read_sql.call_args[1]['params']
    
    assert "LOWER(vs.vm_name) LIKE LOWER(:search)" in sql_text
    assert params['search'] == "%search_term%"
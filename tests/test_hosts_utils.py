"""
Unit-тесты для src/hosts/hosts_utils.py.
"""
from unittest.mock import MagicMock, patch

import pandas as pd

# Импортируем модуль
from hosts.hosts_utils import (
    fetch_hosts_data,
    load_host_infrastructure_maps,
    process_host_dataframe,
)

# --- Тесты для process_host_dataframe (Чистая логика) ---

def test_process_host_dataframe_basic():
    """Тест базовой обработки: маппинг статусов, имена, колонки."""
    # Сырые данные
    df = pd.DataFrame({
        'vds_id': ['h1', 'h2'],
        'vds_name': ['host1', 'host2'],
        'fqdn': ['h1.local', 'h2.local'],
        'status_code': [3, 4],  # 3=Up, 4=Maintenance (пример)
        'vm_active': [5, None], # None должен стать 0
        'cluster_id': ['c1', 'c2'],
        'storage_pool_id': ['dc1', 'dc2'],
        'is_spm': [True, False],
    })
    
    clusters = {'c1': 'Cluster-One', 'c2': 'Cluster-Two'}
    dc_map = {'dc1': 'DC-One', 'dc2': 'DC-Two'}
    
    result = process_host_dataframe(df, clusters, dc_map, show_problems=False)
    
    # Проверка колонок
    assert list(result.columns) == [
        'Имя хоста', 'FQDN', 'ID', 'Статус', '_status_code',
        'SPM', 'Активные ВМ', 'Кластер', 'Дата-центр',
    ]
    
    # Проверка данных
    row1 = result.iloc[0]
    assert row1['Имя хоста'] == 'host1'
    assert row1['Статус'] == 'Up'
    assert row1['_status_code'] == 3
    assert row1['Активные ВМ'] == 5
    assert row1['Кластер'] == 'Cluster-One'
    assert row1['Дата-центр'] == 'DC-One'
    assert row1['SPM'] == 'SPM'
    
    row2 = result.iloc[1]
    assert row2['Активные ВМ'] == 0  # None -> 0
    assert row2['Статус'] == 'NonResponsive'
    assert row2['SPM'] == '—'


def test_process_host_dataframe_health_filter_maintenance():
    df = pd.DataFrame({
        'vds_id': ['h1', 'h2', 'h3'],
        'vds_name': ['up_host', 'nr_host', 'maint_host'],
        'fqdn': ['f1', 'f2', 'f3'],
        'status_code': [3, 4, 2],
        'vm_active': [1, 0, 0],
        'cluster_id': ['c1', 'c1', 'c1'],
        'storage_pool_id': ['dc1', 'dc1', 'dc1'],
    })
    result = process_host_dataframe(
        df, {'c1': 'C1'}, {'dc1': 'DC1'}, health_filter="maintenance"
    )
    assert list(result['Имя хоста']) == ['maint_host']

def test_process_host_dataframe_filter_problems():
    """Maintenance не считается проблемой; в фильтр попадают только problem-статусы."""
    df = pd.DataFrame({
        'vds_id': ['h1', 'h2', 'h3'],
        'vds_name': ['up_host', 'nr_host', 'maint_host'],
        'fqdn': ['f1', 'f2', 'f3'],
        'status_code': [3, 4, 2],  # Up, NonResponsive, Maintenance
        'vm_active': [1, 0, 0],
        'cluster_id': ['c1', 'c1', 'c1'],
        'storage_pool_id': ['dc1', 'dc1', 'dc1']
    })
    
    clusters = {'c1': 'C1'}
    dc_map = {'dc1': 'DC1'}
    
    result = process_host_dataframe(df, clusters, dc_map, show_problems=True)
    
    assert len(result) == 1
    assert result.iloc[0]['Имя хоста'] == 'nr_host'
    assert 'maint_host' not in result['Имя хоста'].values
    assert 'up_host' not in result['Имя хоста'].values

def test_process_host_dataframe_empty():
    """Тест пустого DataFrame."""
    df = pd.DataFrame()
    result = process_host_dataframe(df, {}, {}, False)
    assert result.empty

# --- Тесты для fetch_hosts_data (SQL логика с моками) ---

@patch("hosts.hosts_utils.pd.read_sql")
@patch("hosts.hosts_utils.get_sqlalchemy_engine")
def test_fetch_hosts_data_no_filters(mock_get_engine, mock_read_sql):
    """Тест запроса без фильтров."""
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame({'vds_id': ['h1']})
    
    filters = ('Все ДЦ', 'Все кластеры', '')
    clusters = {}
    dc_map = {}
    
    df = fetch_hosts_data("test_db", filters, clusters, dc_map)
    
    assert not df.empty
    mock_get_engine.assert_called_once_with("test_db")
    mock_read_sql.assert_called_once()
    
    # Проверяем, что в SQL нет WHERE
    call_args = mock_read_sql.call_args
    sql_text = str(call_args[0][0]) # Первый аргумент - text object
    assert "WHERE" not in sql_text.upper() or "WHERE" in sql_text.upper() and "AND" not in sql_text.upper() 
    # Точнее: если условий нет, WHERE не добавляется вообще в коде: if conditions: base_sql += " WHERE ..."
    # Значит WHERE не должно быть
    assert "WHERE" not in sql_text
    assert "is_spm" in sql_text
    assert "spm_vds_id" in sql_text
    assert "storage_pool" in sql_text

@patch("hosts.hosts_utils.pd.read_sql")
@patch("hosts.hosts_utils.get_sqlalchemy_engine")
def test_fetch_hosts_data_with_search(mock_get_engine, mock_read_sql):
    """Тест запроса с поиском по имени."""
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame()
    
    filters = ('Все ДЦ', 'Все кластеры', 'myhost')
    clusters = {}
    dc_map = {}
    
    fetch_hosts_data("test_db", filters, clusters, dc_map)
    
    call_args = mock_read_sql.call_args
    sql_text = str(call_args[0][0])
    params = call_args[1]['params']
    
    assert "LIKE" in sql_text.upper()
    assert params['search'] == "%myhost%"

@patch("hosts.hosts_utils.pd.read_sql")
@patch("hosts.hosts_utils.get_sqlalchemy_engine")
def test_fetch_hosts_data_with_dc_filter(mock_get_engine, mock_read_sql):
    """Тест фильтрации по Дата-центру."""
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    mock_read_sql.return_value = pd.DataFrame()
    
    filters = ('MyDC', 'Все кластеры', '')
    clusters = {}
    dc_map = {'dc_uuid_1': 'MyDC'} # Обратный маппинг для поиска ID по имени
    
    fetch_hosts_data("test_db", filters, clusters, dc_map)
    
    call_args = mock_read_sql.call_args
    sql_text = str(call_args[0][0])
    params = call_args[1]['params']
    
    assert "c.storage_pool_id = :dc_id" in sql_text
    assert params['dc_id'] == 'dc_uuid_1'

# --- Тесты для load_host_infrastructure_maps ---

@patch("hosts.hosts_utils.pd.read_sql")
@patch("hosts.hosts_utils.get_sqlalchemy_engine")
def test_load_host_infrastructure_maps(mock_get_engine, mock_read_sql):
    """Тест загрузки маппингов инфраструктуры."""
    mock_engine = MagicMock()
    mock_get_engine.return_value = mock_engine
    
    # Эмулируем два последовательных вызова read_sql
    df_clusters = pd.DataFrame({'cid': ['c1'], 'spid': ['dc1']})
    df_dcs = pd.DataFrame({'dc_id': ['dc1'], 'dc_name': ['DC-One']})
    mock_read_sql.side_effect = [df_clusters, df_dcs]
    
    dc_to_cl, dc_id_to_name, dc_names = load_host_infrastructure_maps("test_db")
    
    assert dc_to_cl == {'dc1': ['c1']}
    assert dc_id_to_name == {'dc1': 'DC-One'}
    assert 'DC-One' in dc_names
    
    mock_engine.dispose.assert_not_called()
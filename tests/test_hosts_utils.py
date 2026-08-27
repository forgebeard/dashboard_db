"""
Unit-тесты для src/hosts/hosts_utils.py.
"""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, ANY
import sys
from pathlib import Path

# Импортируем модуль
from hosts.hosts_utils import (
    process_host_dataframe, 
    fetch_hosts_data, 
    load_host_infrastructure_maps
)
from core.constants import HOST_STATUS_MAP

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
        'storage_pool_id': ['dc1', 'dc2']
    })
    
    clusters = {'c1': 'Cluster-One', 'c2': 'Cluster-Two'}
    dc_map = {'dc1': 'DC-One', 'dc2': 'DC-Two'}
    
    result = process_host_dataframe(df, clusters, dc_map, show_problems=False)
    
    # Проверка колонок
    assert list(result.columns) == ['Имя хоста', 'FQDN', 'ID', 'Статус', 'Активные ВМ', 'Кластер', 'Дата-центр']
    
    # Проверка данных
    row1 = result.iloc[0]
    assert row1['Имя хоста'] == 'host1'
    assert row1['Статус'] == '3 (Up)'  # Предполагаем, что 3 есть в HOST_STATUS_MAP
    assert row1['Активные ВМ'] == 5
    assert row1['Кластер'] == 'Cluster-One'
    assert row1['Дата-центр'] == 'DC-One'
    
    row2 = result.iloc[1]
    assert row2['Активные ВМ'] == 0  # None -> 0
    assert row2['Статус'].startswith('4 (') # Статус 4 должен быть обработан

def test_process_host_dataframe_filter_problems():
    """Тест фильтрации только проблемных хостов."""
    df = pd.DataFrame({
        'vds_id': ['h1', 'h2', 'h3'],
        'vds_name': ['up_host', 'maint_host', 'down_host'],
        'fqdn': ['f1', 'f2', 'f3'],
        'status_code': [3, 4, 2], # 3=Up, остальные - проблемы
        'vm_active': [1, 0, 0],
        'cluster_id': ['c1', 'c1', 'c1'],
        'storage_pool_id': ['dc1', 'dc1', 'dc1']
    })
    
    clusters = {'c1': 'C1'}
    dc_map = {'dc1': 'DC1'}
    
    result = process_host_dataframe(df, clusters, dc_map, show_problems=True)
    
    # Должны остаться только h2 и h3 (статусы != 3)
    assert len(result) == 2
    assert 'up_host' not in result['Имя хоста'].values
    assert 'maint_host' in result['Имя хоста'].values
    assert 'down_host' in result['Имя хоста'].values

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
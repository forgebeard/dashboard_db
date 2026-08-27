# tests/test_storage_utils.py
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
import streamlit as st

# Импортируем тестируемые функции
from storage.storage_utils import load_storage_maps, process_storage_dataframe


# --- FIXTURES ---

@pytest.fixture
def mock_db_config():
    """Базовый конфиг БД для моков."""
    return {"host": "localhost", "port": 5432, "db": "engine", "user": "u", "pass": "p"}


@pytest.fixture
def raw_storage_df():
    """Сырой датафрейм, имитирующий ответ из БД oVirt."""
    return pd.DataFrame({
        'storage_name': ['data_domain_1', 'iso_domain', 'broken_domain'],
        'sd_id': ['uuid-1', 'uuid-2', 'uuid-3'],
        'storage_domain_type': [0, 1, 99],      # 0=Data, 1=ISO, 99=Unknown
        'storage_type': [0, 1, 5],             # 0=NFS, 1=iSCSI, 5=Unknown
        'shared_status_code': [0, 3, -1],      # 0=Active, 3=Maintenance, -1=Unknown
        'dc_name': ['DC_PROD', 'DC_ISO', 'DC_BROKEN'],
        'available_disk_size': [1000, 500, 100],
        'used_disk_size': [800, 100, 200]      # В broken_domain used > available (баг данных)
    })


# --- TESTS: load_storage_maps ---

class TestLoadStorageMaps:
    
    @patch('storage.storage_utils.get_sqlalchemy_engine')
    @patch('storage.storage_utils.pd.read_sql')
    def test_load_success(self, mock_read_sql, mock_get_engine, mock_db_config):
        """Успешная загрузка маппинга ДЦ."""
        # Arrange
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        
        mock_read_sql.return_value = pd.DataFrame({
            'dc_id': ['id-1', 'id-2'],
            'dc_name': ['DC_A', 'DC_B']
        })
        
        # Act
        id_map, name_set = load_storage_maps(mock_db_config)
        
        # Assert
        assert id_map == {'id-1': 'DC_A', 'id-2': 'DC_B'}
        assert name_set == {'DC_A', 'DC_B'}
        mock_engine.dispose.assert_not_called()
        
        # Проверяем, что SQL запрос корректен (приведение типов ::text)
        call_args = mock_read_sql.call_args[0][0]
        assert "id::text" in str(call_args)

    @patch('storage.storage_utils.st.warning')
    @patch('storage.storage_utils.get_sqlalchemy_engine')
    def test_load_exception_handling(self, mock_get_engine, mock_warning, mock_db_config):
        """При ошибке БД функция должна вернуть пустые структуры и показать warning."""
        # Arrange
        mock_get_engine.side_effect = Exception("Connection refused")
        
        # Act
        id_map, name_set = load_storage_maps(mock_db_config)
        
        # Assert
        assert id_map == {}
        assert name_set == set()
        mock_warning.assert_called_once()
        assert "Не удалось загрузить связи ДЦ" in mock_warning.call_args[0][0]


# --- TESTS: process_storage_dataframe ---

class TestProcessStorageDataframe:
    
    def test_empty_dataframe(self):
        """Пустой вход должен возвращать пустой выход без ошибок."""
        result = process_storage_dataframe(pd.DataFrame())
        assert result.empty
    
    @patch('storage.storage_utils.STORAGE_DOMAIN_TYPE_MAP', {0: 'Data', 1: 'ISO'})
    @patch('storage.storage_utils.STORAGE_TYPE_MAP', {0: 'NFS', 1: 'iSCSI'})
    @patch('storage.storage_utils.SHARED_STATUS_MAP', {0: 'Active', 3: 'Maintenance'})
    def test_processing_logic(self, raw_storage_df):
        """Проверка маппинга, расчетов и переименования колонок."""
        # Act
        result = process_storage_dataframe(raw_storage_df)
        
        # Assert: Структура
        expected_cols = ['Имя домена', 'UUID', 'Тип домена', 'Тип хранилища', 
                         'Статус', 'Дата-центр', 'Заполнено (%)', 'Всего (ГБ)', 'Свободно (ГБ)']
        assert list(result.columns) == expected_cols
        
        # Assert: Маппинг значений
        assert result.iloc[0]['Тип домена'] == 'Data'
        assert result.iloc[1]['Тип хранилища'] == 'iSCSI'
        assert result.iloc[2]['Статус'] == 'Unknown'  # Код -1 нет в карте
        assert result.iloc[0]['Тип хранилища'] == 'NFS'
        
        # Assert: Математика
        # Нормальный случай: 800/1000 = 80%
        assert result.iloc[0]['Заполнено (%)'] == 80.0
        assert result.iloc[0]['Свободно (ГБ)'] == 200.0
        
        # Баг данных: used(200) > total(100). Должно клипповаться до 100%
        assert result.iloc[2]['Заполнено (%)'] == 100.0
        # Свободно должно быть отрицательным или нулем? 
        # В коде: (total - used) -> 100 - 200 = -100. Это ок для диагностики.
        assert result.iloc[2]['Свободно (ГБ)'] == -100.0 

    def test_zero_total_size_handling(self):
        """Деление на ноль при available_disk_size = 0."""
        df = pd.DataFrame({
            'storage_name': ['zero_sd'], 'sd_id': ['u1'],
            'storage_domain_type': [0], 'storage_type': [0],
            'shared_status_code': [0], 'dc_name': ['DC'],
            'available_disk_size': [0], 'used_disk_size': [0]
        })
        
        with patch.dict('storage.storage_utils.STORAGE_DOMAIN_TYPE_MAP', {0: 'Data'}), \
             patch.dict('storage.storage_utils.STORAGE_TYPE_MAP', {0: 'NFS'}), \
             patch.dict('storage.storage_utils.SHARED_STATUS_MAP', {0: 'Active'}):
            
            result = process_storage_dataframe(df)
            
            # Не должно быть inf или NaN
            assert result.iloc[0]['Заполнено (%)'] == 0.0
            assert pd.notna(result.iloc[0]['Заполнено (%)'])

    def test_non_numeric_size_coercion(self):
        """Некорректные строки в размерах должны становиться 0."""
        df = pd.DataFrame({
            'storage_name': ['bad_sd'], 'sd_id': ['u1'],
            'storage_domain_type': [0], 'storage_type': [0],
            'shared_status_code': [0], 'dc_name': ['DC'],
            'available_disk_size': ['not_a_number'], 
            'used_disk_size': [None]
        })
        
        with patch.dict('storage.storage_utils.STORAGE_DOMAIN_TYPE_MAP', {0: 'Data'}), \
             patch.dict('storage.storage_utils.STORAGE_TYPE_MAP', {0: 'NFS'}), \
             patch.dict('storage.storage_utils.SHARED_STATUS_MAP', {0: 'Active'}):
            
            result = process_storage_dataframe(df)
            
            # coerce -> NaN -> fillna(0)
            assert result.iloc[0]['Всего (ГБ)'] == 0.0
            assert result.iloc[0]['Заполнено (%)'] == 0.0
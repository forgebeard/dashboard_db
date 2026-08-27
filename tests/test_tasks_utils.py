# tests/test_tasks_utils.py
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta
import os

# Импортируем тестируемые модули
from tasks.tasks_diagnostics import render_tasks_diagnostics
from tasks.tasks_module import render_tasks_list
from tasks.task_inspector_sql import get_task_inspector_report, _fmt_date


# --- FIXTURES ---

@pytest.fixture
def mock_active_db():
    return "test_engine_db"


@pytest.fixture
def mock_infra_maps():
    """Мок карт инфраструктуры для фильтров."""
    return {
        "dc_id_to_name": {"dc-1": "DC_PROD"},
        "cluster_id_to_name": {"cl-1": "Cluster_A"},
        "host_id_to_name": {"h-1": "Host_A"},
        "dc_to_clusters": {"dc-1": ["cl-1"]},
        "cluster_to_hosts": {"cl-1": ["h-1"]}
    }


# --- TESTS: tasks_diagnostics.py ---

class TestTasksDiagnostics:
    
    @patch("core.table_preview.st")
    @patch("core.table_preview.get_sqlalchemy_engine")
    @patch("core.table_preview.pd.read_sql_query")
    def test_render_success(self, mock_read_sql, mock_get_engine, mock_st, mock_active_db):
        """Базовая проверка: функция отрабатывает без ошибок, кэшированный engine не dispose."""
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_read_sql.return_value = pd.DataFrame({"id": [1]})
        mock_st.number_input.return_value = 100

        render_tasks_diagnostics(mock_active_db)

        mock_engine.dispose.assert_not_called()
        assert mock_st.expander.call_count > 10

    @patch("core.table_preview.st")
    @patch("core.table_preview.get_sqlalchemy_engine")
    def test_render_connection_error(self, mock_get_engine, mock_st, mock_active_db):
        """При ошибке подключения должна быть st.error, а не исключение."""
        mock_get_engine.side_effect = Exception("DB Down")
        mock_st.number_input.return_value = 100

        render_tasks_diagnostics(mock_active_db)

        mock_st.error.assert_called()
        assert "Не удалось подключиться" in str(mock_st.error.call_args)


# --- TESTS: tasks_module.py (SQL Generation Logic) ---

class TestTasksModuleSQL:
    
    def _setup_st_mocks(self, mock_st):
        """Настраивает моки для st.columns и виджетов."""
        # columns([1,1,1,2]) -> 4 мока
        mock_st.columns.side_effect = [
            [MagicMock(), MagicMock(), MagicMock(), MagicMock()],  # Строка 1: фильтры
            [MagicMock(), MagicMock(), MagicMock()]               # Строка 2: время/поиск
        ]
        # selectbox: DC, Cluster, Host
        mock_st.selectbox.side_effect = ['Все ДЦ', 'Все кластеры', 'Host_A']
        # text_input: vm_search, task_id_search
        mock_st.text_input.side_effect = ['', '']
        # datetime_input: start, end
        mock_st.datetime_input.side_effect = [None, None]
        # dataframe selection (пустой по умолчанию)
        mock_event = MagicMock()
        mock_event.selection.rows = []
        mock_st.dataframe.return_value = mock_event
    
    @patch('tasks.tasks_module.st')
    @patch('tasks.tasks_module.get_sqlalchemy_engine')
    @patch('tasks.tasks_module.load_audit_infrastructure_maps')
    @patch('tasks.tasks_module.pd.read_sql')
    def test_sql_generation_with_host_filter(
        self, mock_read_sql, mock_load_maps, mock_get_engine, mock_st, 
        mock_active_db, mock_infra_maps
    ):
        """Проверка: при выборе хоста SQL должен содержать фильтр по correlation_id."""
        mock_load_maps.return_value = mock_infra_maps
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        
        self._setup_st_mocks(mock_st)
        
        # Первый вызов read_sql - поиск correlation_id
        df_corr = pd.DataFrame({'correlation_id': ['corr-uuid-1', 'corr-uuid-2']})
        # Второй вызов - основные задачи
        df_tasks = pd.DataFrame({
            'task_id': ['t1'], 'action_type': [1], 'status': [1], 'result': [0],
            'started_at': [datetime.now()], 'vdsm_task_id_txt': ['v1'],
            'root_command_id': ['r1'], 'command_type': ['CreateVM']
        })
        mock_read_sql.side_effect = [df_corr, df_tasks]
        
        render_tasks_list(mock_active_db)
        
        # Проверяем второй вызов pd.read_sql (основной запрос)
        main_call = mock_read_sql.call_args_list[1]
        sql_text = str(main_call[0][0])  # text() object -> string
        
        # Должен быть фильтр по IN :corr_ids
        assert "IN :corr_ids" in sql_text or "IN (" in sql_text
        params = main_call[1]['params']
        assert 'corr_ids' in params
        assert len(params['corr_ids']) == 2

    @patch('tasks.tasks_module.st')
    @patch('tasks.tasks_module.get_sqlalchemy_engine')
    @patch('tasks.tasks_module.load_audit_infrastructure_maps')
    @patch('tasks.tasks_module.pd.read_sql')
    def test_empty_correlation_ids_returns_nothing(
        self, mock_read_sql, mock_load_maps, mock_get_engine, mock_st,
        mock_active_db, mock_infra_maps
    ):
        """Если фильтры заданы, но связей нет (пустой df_corr), SQL должен содержать AND 1=0."""
        mock_load_maps.return_value = mock_infra_maps
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        
        self._setup_st_mocks(mock_st)
        
        # Пустой результат поиска корреляций
        mock_read_sql.side_effect = [pd.DataFrame(), pd.DataFrame()]
        
        render_tasks_list(mock_active_db)
        
        main_call = mock_read_sql.call_args_list[1]
        sql_text = str(main_call[0][0])
        assert "AND 1=0" in sql_text


# --- TESTS: task_inspector_sql.py ---

class TestTaskInspector:
    
    def test_fmt_date_none(self):
        assert _fmt_date(None) == "—"
        
    def test_fmt_date_valid(self):
        dt = datetime(2024, 5, 1, 10, 30, 0)
        assert _fmt_date(dt) == "01.05.2024 10:30:00"

    @patch("tasks.task_inspector_sql.InspectorBase")
    def test_report_task_not_found(self, mock_ib):
        """Задача не найдена -> возврат error dict."""
        mock_insp = MagicMock()
        mock_insp.fetch_one.return_value = None
        mock_ib.return_value.__enter__.return_value = mock_insp

        result = get_task_inspector_report("db", "non-existent-id")

        assert "error" in result
        assert "не найдена" in result["error"].lower()

    @patch("tasks.task_inspector_sql.InspectorBase")
    def test_report_success_with_audit_logs(self, mock_ib):
        """Успешная генерация отчета с сопутствующими событиями."""
        task_data = {
            "task_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "action_type": 100,
            "status": 1,
            "result": 0,
            "started_at": datetime(2024, 6, 15, 12, 0, 0),
            "storage_pool_id": "sp-uuid",
            "task_type": "VDSM",
            "vdsm_task_id": "vdsm-uuid",
            "root_command_id": "cmd-uuid",
            "user_id": "user-uuid",
            "command_type": "CreateSnapshot",
            "cmd_status": 1,
            "created_at": datetime(2024, 6, 15, 11, 59, 0),
            "command_parameters": '{"vmId": "123"}',
            "data": None,
        }
        audit_logs = [
            {
                "log_time": datetime(2024, 6, 15, 12, 0, 30),
                "log_type_name": "USER_CREATE_SNAPSHOT",
                "vm_name": "TestVM",
                "vds_name": "Host1",
                "message": "Started",
            }
        ]
        mock_insp = MagicMock()
        mock_insp.fetch_one.return_value = task_data
        mock_insp.fetch_all.return_value = audit_logs
        mock_ib.return_value.__enter__.return_value = mock_insp

        result = get_task_inspector_report("db", "aaaa...")

        assert "report_text" in result
        report = result["report_text"]
        assert "TASK-INSPECTOR" in report
        assert "CreateSnapshot" in report
        assert "USER_CREATE_SNAPSHOT" in report
        assert "TestVM" in report
        assert "... (данные обрезаны)" not in report
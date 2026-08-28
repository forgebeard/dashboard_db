# tests/test_tasks_utils.py
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime

from tasks.tasks_diagnostics import render_tasks_diagnostics
from tasks.tasks_module import render_tasks_list
from tasks.tasks_utils import (
    build_audit_correlation_sql,
    format_tasks_dataframe,
)


@pytest.fixture
def mock_active_db():
    return "test_engine_db"


@pytest.fixture
def mock_infra_maps():
    return {
        "dc_id_to_name": {"dc-1": "DC_PROD"},
        "cluster_id_to_name": {"cl-1": "Cluster_A"},
        "host_id_to_name": {"h-1": "Host_A", "h-2": "Host_B"},
        "dc_to_clusters": {"dc-1": ["cl-1"]},
        "cluster_to_hosts": {"cl-1": ["h-1", "h-2"]},
    }


class TestTasksDiagnostics:

    @patch("core.table_preview.st")
    @patch("core.table_preview.get_sqlalchemy_engine")
    @patch("core.table_preview.pd.read_sql_query")
    def test_render_success(self, mock_read_sql, mock_get_engine, mock_st, mock_active_db):
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_read_sql.return_value = pd.DataFrame({"id": [1]})
        mock_st.number_input.return_value = 100
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        render_tasks_diagnostics(mock_active_db)

        mock_engine.dispose.assert_not_called()
        assert mock_st.expander.call_count > 10

    @patch("core.table_preview.st")
    @patch("core.table_preview.get_sqlalchemy_engine")
    def test_render_connection_error(self, mock_get_engine, mock_st, mock_active_db):
        mock_get_engine.side_effect = Exception("DB Down")
        mock_st.number_input.return_value = 100
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        render_tasks_diagnostics(mock_active_db)

        mock_st.error.assert_called()
        assert "Не удалось подключиться" in str(mock_st.error.call_args)


class TestTasksCorrelationSQL:

    def test_dc_host_ids_in(self):
        sql, params = build_audit_correlation_sql(host_ids=["h-1", "h-2"])
        assert "vds_id::text IN :h_ids" in sql
        assert params["h_ids"] == ("h-1", "h-2")

    def test_empty_host_ids(self):
        sql, params = build_audit_correlation_sql(host_ids=[])
        assert "AND 1=0" in sql
        assert "h_ids" not in params

    def test_no_host_slice(self):
        sql, params = build_audit_correlation_sql(host_ids=None, vm_search="web")
        assert "vds_id" not in sql
        assert params["vm_t"] == "%web%"


class TestFormatTasksDataframe:

    def test_columns_and_status_labels(self):
        df = pd.DataFrame({
            "task_id": ["t1"],
            "action_type": [261],
            "status": [2],
            "result": [0],
            "started_at": [datetime(2024, 6, 15, 12, 0, 0)],
            "vdsm_task_id_txt": ["v1"],
            "root_command_id": ["r1"],
            "command_type": [None],
        })
        show = format_tasks_dataframe(df)
        assert list(show.columns) == ["Начато", "Команда", "Статус", "Результат"]
        assert show.iloc[0]["Команда"] == "ConvertDisk"
        assert show.iloc[0]["Статус"] == "running"
        assert show.iloc[0]["Результат"] == "success"
        assert "Task ID" not in show.columns
        assert "Action Code" not in show.columns
        assert "Result" not in show.columns


class TestTasksModuleSQL:

    def _setup_st_mocks(self, mock_st, select_side_effect):
        mock_st.columns.side_effect = [
            [MagicMock(), MagicMock(), MagicMock(), MagicMock()],
            [MagicMock(), MagicMock(), MagicMock()],
        ]
        mock_st.selectbox.side_effect = select_side_effect
        mock_st.text_input.side_effect = ["", ""]
        mock_st.datetime_input.side_effect = [None, None]
        mock_st.dataframe.return_value = None

    @patch("tasks.tasks_module.st")
    @patch("tasks.tasks_module.get_sqlalchemy_engine")
    @patch("tasks.tasks_module.load_audit_infrastructure_maps")
    @patch("tasks.tasks_module.pd.read_sql")
    def test_sql_generation_with_host_filter(
        self, mock_read_sql, mock_load_maps, mock_get_engine, mock_st,
        mock_active_db, mock_infra_maps
    ):
        mock_load_maps.return_value = mock_infra_maps
        mock_get_engine.return_value = MagicMock()
        self._setup_st_mocks(mock_st, ["Все ДЦ", "Все кластеры", "Host_A"])

        df_corr = pd.DataFrame({"correlation_id": ["corr-uuid-1", "corr-uuid-2"]})
        df_tasks = pd.DataFrame({
            "task_id": ["t1"], "action_type": [1], "status": [1], "result": [0],
            "started_at": [datetime.now()], "vdsm_task_id_txt": ["v1"],
            "root_command_id": ["r1"], "command_type": ["CreateVM"]
        })
        mock_read_sql.side_effect = [df_corr, df_tasks]

        render_tasks_list(mock_active_db)

        corr_sql = str(mock_read_sql.call_args_list[0][0][0])
        assert "IN :h_ids" in corr_sql
        assert mock_read_sql.call_args_list[0][1]["params"]["h_ids"] == ("h-1",)

        main_call = mock_read_sql.call_args_list[1]
        sql_text = str(main_call[0][0])
        assert "IN :corr_ids" in sql_text or "IN (" in sql_text
        params = main_call[1]["params"]
        assert "corr_ids" in params
        assert len(params["corr_ids"]) == 2

        mock_st.dataframe.assert_called_once()
        kwargs = mock_st.dataframe.call_args.kwargs
        assert "on_select" not in kwargs

    @patch("tasks.tasks_module.st")
    @patch("tasks.tasks_module.get_sqlalchemy_engine")
    @patch("tasks.tasks_module.load_audit_infrastructure_maps")
    @patch("tasks.tasks_module.pd.read_sql")
    def test_dc_filter_uses_all_cluster_hosts(
        self, mock_read_sql, mock_load_maps, mock_get_engine, mock_st,
        mock_active_db, mock_infra_maps
    ):
        mock_load_maps.return_value = mock_infra_maps
        mock_get_engine.return_value = MagicMock()
        self._setup_st_mocks(mock_st, ["DC_PROD", "Все кластеры", "Все хосты"])
        mock_read_sql.side_effect = [
            pd.DataFrame({"correlation_id": ["c1"]}),
            pd.DataFrame({
                "task_id": ["t1"], "action_type": [1], "status": [1], "result": [0],
                "started_at": [datetime.now()], "vdsm_task_id_txt": ["v1"],
                "root_command_id": ["r1"], "command_type": ["CreateVM"]
            }),
        ]

        render_tasks_list(mock_active_db)

        corr_params = mock_read_sql.call_args_list[0][1]["params"]
        assert corr_params["h_ids"] == ("h-1", "h-2")

    @patch("tasks.tasks_module.st")
    @patch("tasks.tasks_module.get_sqlalchemy_engine")
    @patch("tasks.tasks_module.load_audit_infrastructure_maps")
    @patch("tasks.tasks_module.pd.read_sql")
    def test_empty_correlation_ids_returns_nothing(
        self, mock_read_sql, mock_load_maps, mock_get_engine, mock_st,
        mock_active_db, mock_infra_maps
    ):
        mock_load_maps.return_value = mock_infra_maps
        mock_get_engine.return_value = MagicMock()
        self._setup_st_mocks(mock_st, ["Все ДЦ", "Все кластеры", "Host_A"])
        mock_read_sql.side_effect = [pd.DataFrame(), pd.DataFrame()]

        render_tasks_list(mock_active_db)

        main_call = mock_read_sql.call_args_list[1]
        sql_text = str(main_call[0][0])
        assert "AND 1=0" in sql_text


def test_task_inspector_not_imported():
    with pytest.raises(ImportError):
        import tasks.task_inspector_sql  # noqa: F401

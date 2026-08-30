# tests/test_tasks_utils.py
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tasks.tasks_diagnostics import render_tasks_diagnostics
from tasks.tasks_module import render_tasks_list
from tasks.tasks_utils import (
    build_audit_correlation_sql,
    build_task_entities_sql,
    format_tasks_dataframe,
    process_task_entities,
    process_tasks_dataframe,
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
    @patch("core.table_preview.read_sql_df")
    def test_render_success(self, mock_read_sql, mock_get_engine, mock_st, mock_active_db):
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_read_sql.return_value = pd.DataFrame({"id": [1]})
        mock_st.number_input.return_value = 100
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        render_tasks_diagnostics(mock_active_db)

        mock_engine.dispose.assert_not_called()
        assert mock_st.expander.call_count == 9

    @patch("core.table_preview.st")
    @patch("core.table_preview.get_sqlalchemy_engine")
    def test_render_connection_error(self, mock_get_engine, mock_st, mock_active_db):
        from core.exceptions import DataLoadError

        mock_get_engine.side_effect = DataLoadError("DB Down")
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
        assert list(show.columns)[:6] == [
            "Начато", "Команда", "UUID", "correlation", "Статус", "Результат",
        ]
        assert show.iloc[0]["Команда"] == "ConvertDisk"
        assert show.iloc[0]["Статус"] == "running"
        assert show.iloc[0]["Результат"] == "success"
        assert show.iloc[0]["UUID"] == "t1"
        assert show.iloc[0]["correlation"] == "r1"
        assert "Task ID" not in show.columns
        assert "Action Code" not in show.columns
        assert "Result" not in show.columns

    def test_pills_are_mutually_exclusive(self):
        df = pd.DataFrame({
            "task_id": ["a", "b", "c", "d"],
            "action_type": [261, 261, 261, 261],
            "status": [2, 3, 3, 0],
            "result": [0, 0, 1, 0],
            "started_at": [datetime(2024, 6, 15, 12, 0, 0)] * 4,
            "vdsm_task_id_txt": ["v"] * 4,
            "root_command_id": ["r"] * 4,
            "command_type": [None] * 4,
        })
        running = process_tasks_dataframe(df, health_filter="running")
        finished = process_tasks_dataframe(df, health_filter="finished")
        errors = process_tasks_dataframe(df, health_filter="errors")
        assert list(running["UUID"]) == ["a"]
        assert list(finished["UUID"]) == ["b"]
        assert set(errors["UUID"]) == {"c", "d"}
        ids = set(running["UUID"]) | set(finished["UUID"]) | set(errors["UUID"])
        assert ids == {"a", "b", "c", "d"}


class TestTaskEntities:

    def test_sql_uses_task_id_and_storage_join(self):
        sql, params = build_task_entities_sql("t-1")
        assert "FROM async_tasks_entities" in sql
        assert "storage_domain_static" in sql
        assert "async_task_id::text = :tid" in sql
        assert "FROM job" not in sql
        assert params == {"tid": "t-1"}

    def test_empty_entities(self):
        table = process_task_entities(pd.DataFrame())
        assert list(table.columns) == ["Тип", "Объект"]
        assert table.empty

    def test_storage_name(self):
        entities = pd.DataFrame(
            {
                "entity_type": ["Storage"],
                "entity_id": ["4cb76720-d04e-4e4d-ae19-de42770a91b2"],
                "entity_name": ["Dat1"],
            }
        )
        table = process_task_entities(entities)
        assert list(table.iloc[0]) == ["Storage", "Dat1"]


class TestTasksModuleSQL:

    def _setup_st_mocks(self, mock_st, select_side_effect, mock_ui_st):
        def _cols(*args, **kwargs):
            spec = args[0] if args else 4
            n = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
            return [MagicMock() for _ in range(n)]

        state = {}
        mock_st.columns.side_effect = _cols
        mock_st.selectbox.side_effect = select_side_effect
        mock_st.text_input.side_effect = ["", ""]
        mock_st.datetime_input.side_effect = [None, None]
        event = MagicMock()
        event.selection.rows = []
        mock_st.dataframe.return_value = event
        mock_st.session_state = state
        mock_st.segmented_control.return_value = "all"
        mock_st.container.return_value.__enter__.return_value = MagicMock()
        mock_st.container.return_value.__exit__.return_value = False
        mock_ui_st.columns.side_effect = _cols
        mock_ui_st.session_state = state
        mock_ui_st.segmented_control.return_value = "all"
        mock_ui_st.container.return_value = mock_st.container.return_value
        mock_ui_st.subheader = MagicMock()
        mock_ui_st.caption = MagicMock()
        mock_ui_st.button = MagicMock()

    @patch("core.ui_utils.st")
    @patch("tasks.tasks_module.st")
    @patch("tasks.tasks_module.load_audit_infrastructure_maps")
    @patch("tasks.tasks_module.load_sql_df")
    def test_sql_generation_with_host_filter(
        self, mock_load, mock_load_maps, mock_st, mock_ui_st,
        mock_active_db, mock_infra_maps
    ):
        mock_load_maps.return_value = mock_infra_maps
        self._setup_st_mocks(mock_st, ["Все ДЦ", "Все кластеры", "Host_A"], mock_ui_st)

        df_corr = pd.DataFrame({"correlation_id": ["corr-uuid-1", "corr-uuid-2"]})
        df_tasks = pd.DataFrame({
            "task_id": ["t1"], "action_type": [1], "status": [1], "result": [0],
            "started_at": [datetime.now()], "vdsm_task_id_txt": ["v1"],
            "root_command_id": ["r1"], "command_type": ["CreateVM"]
        })
        mock_load.side_effect = [df_corr, df_tasks]

        render_tasks_list(mock_active_db)

        corr_sql = str(mock_load.call_args_list[0][0][1])
        assert "IN :h_ids" in corr_sql
        assert mock_load.call_args_list[0][1]["params"]["h_ids"] == ("h-1",)

        main_call = mock_load.call_args_list[1]
        sql_text = str(main_call[0][1])
        assert "IN :corr_ids" in sql_text or "IN (" in sql_text
        params = main_call[1]["params"]
        assert "corr_ids" in params
        assert len(params["corr_ids"]) == 2

        mock_st.dataframe.assert_called_once()
        kwargs = mock_st.dataframe.call_args.kwargs
        assert kwargs.get("on_select") == "rerun"

    @patch("core.ui_utils.st")
    @patch("tasks.tasks_module.st")
    @patch("tasks.tasks_module.load_audit_infrastructure_maps")
    @patch("tasks.tasks_module.load_sql_df")
    def test_dc_filter_uses_all_cluster_hosts(
        self, mock_load, mock_load_maps, mock_st, mock_ui_st,
        mock_active_db, mock_infra_maps
    ):
        mock_load_maps.return_value = mock_infra_maps
        self._setup_st_mocks(mock_st, ["DC_PROD", "Все кластеры", "Все хосты"], mock_ui_st)
        mock_load.side_effect = [
            pd.DataFrame({"correlation_id": ["c1"]}),
            pd.DataFrame({
                "task_id": ["t1"], "action_type": [1], "status": [1], "result": [0],
                "started_at": [datetime.now()], "vdsm_task_id_txt": ["v1"],
                "root_command_id": ["r1"], "command_type": ["CreateVM"]
            }),
        ]

        render_tasks_list(mock_active_db)

        corr_params = mock_load.call_args_list[0][1]["params"]
        assert corr_params["h_ids"] == ("h-1", "h-2")

    @patch("core.ui_utils.st")
    @patch("tasks.tasks_module.st")
    @patch("tasks.tasks_module.load_audit_infrastructure_maps")
    @patch("tasks.tasks_module.load_sql_df")
    def test_empty_correlation_ids_returns_nothing(
        self, mock_load, mock_load_maps, mock_st, mock_ui_st,
        mock_active_db, mock_infra_maps
    ):
        mock_load_maps.return_value = mock_infra_maps
        self._setup_st_mocks(mock_st, ["Все ДЦ", "Все кластеры", "Host_A"], mock_ui_st)
        mock_load.side_effect = [pd.DataFrame(), pd.DataFrame()]

        render_tasks_list(mock_active_db)

        main_call = mock_load.call_args_list[1]
        sql_text = str(main_call[0][1])
        assert "AND 1=0" in sql_text

    @patch("core.ui_utils.st")
    @patch("tasks.tasks_module.st")
    @patch("tasks.tasks_module.load_audit_infrastructure_maps")
    @patch("tasks.tasks_module.load_sql_df")
    def test_correlation_load_error_fail_closed(
        self, mock_load, mock_load_maps, mock_st, mock_ui_st,
        mock_active_db, mock_infra_maps
    ):
        from core.exceptions import DataLoadError

        mock_load_maps.return_value = mock_infra_maps
        self._setup_st_mocks(mock_st, ["Все ДЦ", "Все кластеры", "Host_A"], mock_ui_st)
        mock_load.side_effect = DataLoadError("timeout")

        render_tasks_list(mock_active_db)

        assert mock_load.call_count == 1
        mock_ui_st.error.assert_called()
        mock_st.dataframe.assert_not_called()

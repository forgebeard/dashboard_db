"""Юнит-тесты для src/core/table_preview.py."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.exceptions import DataLoadError
from core.table_preview import assert_safe_ident, render_grouped_table_preview


@pytest.mark.parametrize("name", ["vds_static", "_tmp", "A1"])
def test_assert_safe_ident_ok(name):
    assert assert_safe_ident(name) == name


@pytest.mark.parametrize("name", ["vds;drop", "public.vds", "vds static", "1abc", ""])
def test_assert_safe_ident_rejects(name):
    with pytest.raises(ValueError):
        assert_safe_ident(name)


def _preview_st_mocks(mock_st: MagicMock) -> None:
    mock_st.number_input.return_value = 100
    mock_st.columns.return_value = [MagicMock(), MagicMock()]


@patch("core.table_preview.st")
@patch("core.table_preview.get_sqlalchemy_engine")
@patch("core.table_preview.read_sql_df")
def test_empty_table_still_renders_column_headers(mock_read_sql, _mock_engine, mock_st):
    empty = pd.DataFrame(columns=["backup_id", "is_live_backup"])
    mock_read_sql.return_value = empty
    _preview_st_mocks(mock_st)

    render_grouped_table_preview(
        "dump_db",
        {"": {"vm_backups": "Резервные копии ВМ"}},
        title="Таблицы",
        limit_key="lim_dump_db",
    )

    mock_st.info.assert_not_called()
    mock_st.dataframe.assert_called_once()
    shown = mock_st.dataframe.call_args.args[0]
    assert list(shown.columns) == ["backup_id", "is_live_backup"]
    assert shown.empty
    mock_st.caption.assert_called_once()
    assert mock_st.caption.call_args.args[0] == "0 записей в `vm_backups`"


@patch("core.table_preview.st")
@patch("core.table_preview.get_sqlalchemy_engine")
@patch("core.table_preview.read_sql_df")
def test_nonempty_table_keeps_row_caption(mock_read_sql, _mock_engine, mock_st):
    mock_read_sql.return_value = pd.DataFrame({"backup_id": ["a"]})
    _preview_st_mocks(mock_st)

    render_grouped_table_preview(
        "dump_db",
        {"": {"vm_backups": "Резервные копии ВМ"}},
        title="Таблицы",
        limit_key="lim_dump_db",
    )

    mock_st.dataframe.assert_called_once()
    mock_st.caption.assert_called_once()
    assert mock_st.caption.call_args.args[0] == "Показано 1 записей из `vm_backups`"


def _expander_labels(mock_st: MagicMock) -> list[str]:
    return [call.args[0] for call in mock_st.expander.call_args_list]


@patch("core.table_preview.st")
@patch("core.table_preview.get_sqlalchemy_engine")
@patch("core.table_preview.read_sql_df")
def test_preview_skips_host_template_on_73(mock_read_sql, _mock_engine, mock_st):
    mock_read_sql.return_value = pd.DataFrame({"vds_id": ["a"]})
    _preview_st_mocks(mock_st)
    mock_st.session_state = {"cluster_meta": {"engine_release": "РЕД ВИРТ 7.3"}}

    render_grouped_table_preview(
        "dump_db",
        {"": {"vds_static": "Хост", "host_template": "Шаблон"}},
        title="Таблицы",
        limit_key="lim_dump_db",
    )

    labels = _expander_labels(mock_st)
    assert any("vds_static" in label for label in labels)
    assert not any("host_template" in label for label in labels)


@patch("core.table_preview.st")
@patch("core.table_preview.get_sqlalchemy_engine")
@patch("core.table_preview.read_sql_df")
def test_preview_shows_host_template_on_8(mock_read_sql, _mock_engine, mock_st):
    mock_read_sql.return_value = pd.DataFrame({"id": ["a"]})
    _preview_st_mocks(mock_st)
    mock_st.session_state = {"cluster_meta": {"engine_release": "РЕД ВИРТ 8"}}

    render_grouped_table_preview(
        "dump_db",
        {"": {"vds_static": "Хост", "host_template": "Шаблон"}},
        title="Таблицы",
        limit_key="lim_dump_db",
    )

    labels = _expander_labels(mock_st)
    assert any("host_template" in label for label in labels)
    assert mock_read_sql.call_count == 2


@patch("core.table_preview.st")
@patch("core.table_preview.get_sqlalchemy_engine")
@patch("core.table_preview.read_sql_df")
def test_preview_missing_table_is_caption_not_error(mock_read_sql, _mock_engine, mock_st):
    mock_read_sql.side_effect = DataLoadError(
        'relation "host_template" does not exist', kind="undefined_table"
    )
    _preview_st_mocks(mock_st)
    mock_st.session_state = {"cluster_meta": {"engine_release": "РЕД ВИРТ 8"}}

    render_grouped_table_preview(
        "dump_db",
        {"": {"host_template": "Шаблон"}},
        title="Таблицы",
        limit_key="lim_dump_db",
    )

    mock_st.error.assert_not_called()
    mock_st.caption.assert_called()
    assert "нет в этом дампе" in mock_st.caption.call_args.args[0]


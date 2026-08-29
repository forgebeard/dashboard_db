"""Юнит-тесты общих UI-хелперов без импорта app.py."""

import json
from unittest.mock import patch
from uuid import UUID

import pandas as pd

from core.exceptions import DataLoadError
from core.ui_utils import fix_uuid_columns, render_page_header, run_section


@patch("core.ui_utils.st")
def test_run_section_dataloaderror_no_traceback(mock_st):
    def _boom() -> None:
        raise DataLoadError("boom")

    run_section("Хосты", _boom)
    mock_st.error.assert_called_once()
    assert "Хосты" in mock_st.error.call_args[0][0]
    mock_st.exception.assert_not_called()


@patch("core.ui_utils.st")
def test_run_section_other_exception_shows_traceback(mock_st):
    def _boom() -> None:
        raise RuntimeError("ui bug")

    run_section("Хосты", _boom)
    mock_st.error.assert_called_once()
    mock_st.exception.assert_called_once()


@patch("core.ui_utils.st")
def test_render_page_header_includes_release(mock_st):
    mock_st.session_state.get.return_value = {"engine_release": "РЕД ВИРТ 8"}
    render_page_header("Хосты", "67705", details=["4 хостов"])
    mock_st.caption.assert_called_once_with("`67705` · РЕД ВИРТ 8 · 4 хостов")


def test_fix_uuid_columns_stringifies_rv8_cpu_topology():
    topology = {"sockets": [{"cores": [{"cpus": [0, 1]}]}]}
    df = pd.DataFrame(
        {
            "vds_id": [UUID("11111111-1111-1111-1111-111111111111")],
            "cpu_topology": [topology],
            "status": [1],
        }
    )
    out = fix_uuid_columns(df)
    assert out["cpu_topology"].iloc[0] == json.dumps(topology, ensure_ascii=False)
    assert out["vds_id"].iloc[0] == "11111111-1111-1111-1111-111111111111"


def test_fix_uuid_columns_leaves_rv73_without_jsonb():
    df = pd.DataFrame({"vds_id": ["h1"], "cpu_cores": [32]})
    out = fix_uuid_columns(df)
    assert list(out.columns) == ["vds_id", "cpu_cores"]
    assert out["cpu_cores"].iloc[0] == 32


@patch("core.ui_utils.st")
def test_render_page_header_omits_missing_release(mock_st):
    mock_st.session_state.get.return_value = {}
    render_page_header("Хосты", "67705", details=["4 хостов"])
    mock_st.caption.assert_called_once_with("`67705` · 4 хостов")

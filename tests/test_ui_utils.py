"""Юнит-тесты общих UI-хелперов без импорта app.py."""

import json
from unittest.mock import patch
from uuid import UUID

import pandas as pd

from core.config import debug_enabled
from core.exceptions import DataLoadError
from core.ui_utils import fix_uuid_columns, render_page_header, run_section


def test_debug_enabled_from_env(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    assert debug_enabled() is False
    monkeypatch.setenv("DEBUG", "true")
    assert debug_enabled() is True
    monkeypatch.setenv("DEBUG", "1")
    assert debug_enabled() is True
    monkeypatch.setenv("DEBUG", "no")
    assert debug_enabled() is False


@patch("core.ui_utils.st")
def test_run_section_dataloaderror_no_traceback(mock_st):
    def _boom() -> None:
        raise DataLoadError("boom")

    run_section("Хосты", _boom)
    mock_st.error.assert_called_once()
    assert "Хосты" in mock_st.error.call_args[0][0]
    mock_st.exception.assert_not_called()


@patch("core.ui_utils.debug_enabled", return_value=True)
@patch("core.ui_utils.st")
def test_run_section_other_exception_shows_traceback(mock_st, _mock_debug):
    def _boom() -> None:
        raise RuntimeError("ui bug")

    run_section("Хосты", _boom)
    mock_st.error.assert_called_once()
    message = mock_st.error.call_args[0][0]
    assert "Код события:" in message
    assert "ui bug" not in message
    mock_st.exception.assert_called_once()


@patch("core.ui_utils.debug_enabled", return_value=False)
@patch("core.ui_utils.st")
def test_run_section_other_exception_hides_traceback_without_debug(mock_st, _mock_debug):
    def _boom() -> None:
        raise RuntimeError("ui bug")

    run_section("Хосты", _boom)
    mock_st.error.assert_called_once()
    message = mock_st.error.call_args[0][0]
    assert "Код события:" in message
    assert "ui bug" not in message
    mock_st.exception.assert_not_called()


@patch("core.ui_utils.st")
def test_render_page_header_includes_release(mock_st):
    mock_st.session_state.get.return_value = {"engine_release": "РЕД ВИРТ 8"}
    render_page_header("Хосты", "67705", details=["4 хостов"])
    mock_st.caption.assert_called_once_with("`67705` · РЕД ВИРТ 8 · 4 хостов")


@patch("core.ui_utils.st")
def test_render_page_header_includes_engine_and_schema(mock_st):
    mock_st.session_state.get.return_value = {
        "engine_release": "РЕД ВИРТ 7.3",
        "product_version": "7.3.3",
        "schema_version": "04041510",
    }
    render_page_header("Хосты", "67705", details=["4 хостов"])
    mock_st.caption.assert_called_once_with(
        "`67705` · РЕД ВИРТ 7.3 · Engine 7.3.3 · схема БД 04041510 · 4 хостов"
    )


@patch("core.ui_utils.st")
def test_render_page_header_skips_placeholder_versions(mock_st):
    mock_st.session_state.get.return_value = {
        "engine_release": "РЕД ВИРТ 8",
        "product_version": "—",
        "schema_version": "",
    }
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

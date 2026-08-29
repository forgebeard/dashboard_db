"""Юнит-тесты общих UI-хелперов без импорта app.py."""

from unittest.mock import patch

from core.exceptions import DataLoadError
from core.ui_utils import render_page_header, run_section


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


@patch("core.ui_utils.st")
def test_render_page_header_omits_missing_release(mock_st):
    mock_st.session_state.get.return_value = {}
    render_page_header("Хосты", "67705", details=["4 хостов"])
    mock_st.caption.assert_called_once_with("`67705` · 4 хостов")

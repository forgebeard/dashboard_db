"""Юнит-тесты общих UI-хелперов без импорта app.py."""

from unittest.mock import patch

from core.exceptions import DataLoadError
from core.ui_utils import run_section


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

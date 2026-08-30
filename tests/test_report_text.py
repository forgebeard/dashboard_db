"""Тесты оформления текстовых инспекторов."""

from datetime import datetime, timezone

from core.report_text import BAR_DOUBLE, _fmt_date, _fmt_ts, _kv, _kv_at, _yes_no


def test_kv_default_width_matches_vm():
    line = _kv("Имя", "Test1")
    assert line.startswith("  Имя:")
    assert "Test1" in line
    assert _kv_at("    ", "диск", "os") == _kv_at("    ", "диск", "os", width=16)


def test_yes_no_and_bar():
    assert _yes_no(True) == "да"
    assert _yes_no(0) == "нет"
    assert len(BAR_DOUBLE) == 78


def test_fmt_date_empty_and_datetime():
    assert _fmt_date(None) == "—"
    assert _fmt_date("") == "—"
    assert _fmt_date(datetime(2026, 8, 30, 5, 29)) == "30.08.2026 05:29"


def test_fmt_ts_strips_tz():
    assert _fmt_ts(None) == "—"
    aware = datetime(2026, 8, 30, 5, 29, 47, tzinfo=timezone.utc)
    assert _fmt_ts(aware) == "30.08.2026 05:29:47"

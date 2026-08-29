"""Тесты оформления текстовых инспекторов."""

from core.report_text import BAR_DOUBLE, _kv, _kv_at, _yes_no


def test_kv_default_width_matches_vm():
    line = _kv("Имя", "Test1")
    assert line.startswith("  Имя:")
    assert "Test1" in line
    assert _kv_at("    ", "диск", "os") == _kv_at("    ", "диск", "os", width=16)


def test_yes_no_and_bar():
    assert _yes_no(True) == "да"
    assert _yes_no(0) == "нет"
    assert len(BAR_DOUBLE) == 78

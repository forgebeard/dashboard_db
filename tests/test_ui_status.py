"""Юнит-тесты тонов статуса и контракта Problem."""

from core.constants import (
    host_health_counts,
    host_is_maintenance,
    host_is_problem,
    host_status_tone,
    vm_health_counts,
    vm_is_problem,
    vm_status_tone,
)


def test_host_up_is_not_problem():
    assert host_is_problem(3) is False
    assert host_status_tone(3) == "success"


def test_host_maintenance_is_not_problem():
    for code in (2, 8, 9):
        assert host_is_maintenance(code) is True
        assert host_is_problem(code) is False
        assert host_status_tone(code) == "warning"


def test_host_nonresponsive_is_problem():
    assert host_is_problem(4) is True
    assert host_status_tone(4) == "critical"


def test_host_down_is_problem_neutral_tone():
    assert host_is_problem(1) is True
    assert host_status_tone(1) == "neutral"


def test_host_health_counts():
    counts = host_health_counts([3, 3, 2, 4])
    assert counts == {"total": 4, "up": 2, "maintenance": 1, "problems": 1}


def test_vm_problem_down_or_bad_images():
    assert vm_is_problem(1, False) is False
    assert vm_is_problem(0, False) is True
    assert vm_is_problem(1, True) is True


def test_vm_status_tones():
    assert vm_status_tone(1) == "success"
    assert vm_status_tone(0) == "neutral"
    assert vm_status_tone(4) == "warning"
    assert vm_status_tone(8) == "critical"


def test_dataframe_height_fits_few_rows():
    from core.config import DATAFRAME_HEIGHT
    from core.ui_utils import dataframe_height

    assert dataframe_height(4) < DATAFRAME_HEIGHT
    assert dataframe_height(4) < dataframe_height(80)
    assert dataframe_height(200) == DATAFRAME_HEIGHT


def test_vm_health_counts():
    counts = vm_health_counts([1, 0, 4, 1], [False, False, False, True])
    assert counts["total"] == 4
    assert counts["up"] == 2
    assert counts["down"] == 1
    assert counts["paused"] == 1
    assert counts["problems"] == 3

"""Юнит-тесты тонов статуса и контракта Problem."""

from core.constants import (
    ARCHITECTURE_MAP,
    BIOS_TYPE_MAP,
    CLUSTER_STATUS_OK,
    CLUSTER_STATUS_PROBLEMS,
    cluster_health_counts,
    cluster_status_from_hosts,
    cluster_status_tone,
    host_health_counts,
    host_is_maintenance,
    host_is_problem,
    host_status_tone,
    vm_health_counts,
    vm_is_problem,
    vm_layer_tone,
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


def test_vm_problem_excludes_up_and_down():
    assert vm_is_problem(1) is False
    assert vm_is_problem(0) is False
    assert vm_is_problem(4) is True
    assert vm_is_problem(8) is True
    assert vm_is_problem(None) is False


def test_vm_status_tones():
    assert vm_status_tone(1) == "success"
    assert vm_status_tone(0) == "neutral"
    assert vm_status_tone(4) == "warning"
    assert vm_status_tone(8) == "critical"


def test_vm_layer_tones():
    assert vm_layer_tone(None) is None
    assert vm_layer_tone(1) is None
    assert vm_layer_tone(2) == "warning"
    assert vm_layer_tone(4) == "warning"
    assert vm_layer_tone(3) == "critical"


def test_dataframe_height_fits_few_rows():
    from core.config import DATAFRAME_HEIGHT
    from core.ui_utils import dataframe_height

    assert dataframe_height(4) < DATAFRAME_HEIGHT
    assert dataframe_height(4) < dataframe_height(80)
    assert dataframe_height(200) == DATAFRAME_HEIGHT


def test_vm_health_counts():
    counts = vm_health_counts([1, 0, 4, 1])
    assert counts == {"total": 4, "up": 2, "down": 1, "problems": 1}


def test_cluster_status_from_hosts():
    assert cluster_status_from_hosts(0, 0) == CLUSTER_STATUS_OK
    assert cluster_status_from_hosts(None, None) == CLUSTER_STATUS_OK
    assert cluster_status_from_hosts(0, 1) == CLUSTER_STATUS_OK
    assert cluster_status_from_hosts(2, 3) == CLUSTER_STATUS_PROBLEMS


def test_cluster_status_tones():
    assert cluster_status_tone(CLUSTER_STATUS_OK) == "success"
    assert cluster_status_tone(CLUSTER_STATUS_PROBLEMS) == "critical"


def test_cluster_health_counts():
    counts = cluster_health_counts(
        [CLUSTER_STATUS_OK, CLUSTER_STATUS_OK, CLUSTER_STATUS_PROBLEMS]
    )
    assert counts == {"total": 3, "ok": 2, "problems": 1}


def test_architecture_and_bios_maps():
    assert ARCHITECTURE_MAP[1] == "x86_64"
    assert ARCHITECTURE_MAP[0] == "undefined"
    assert BIOS_TYPE_MAP[3] == "Q35 OVMF"

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
    storage_health_counts,
    storage_is_problem,
    storage_status_tone,
    image_health_counts,
    image_is_problem,
    image_status_tone,
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


def test_image_status_contract():
    assert image_is_problem(1) is False
    assert image_is_problem(2) is True
    assert image_is_problem(3) is True
    assert image_is_problem(4) is True
    assert image_is_problem(None) is False
    assert image_status_tone(1) == "success"
    assert image_status_tone(2) == "warning"
    assert image_status_tone(4) == "warning"
    assert image_status_tone(3) == "critical"


def test_image_health_counts():
    counts = image_health_counts([1, 1, 2, 3, None])
    assert counts == {"total": 5, "ok": 2, "problems": 2}


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


def test_storage_shared_status_contract():
    assert storage_is_problem(1) is False
    assert storage_is_problem(0) is True
    assert storage_is_problem(2) is True
    assert storage_is_problem(3) is True
    assert storage_is_problem(None) is False
    assert storage_status_tone(1) == "success"
    assert storage_status_tone(0) == "neutral"
    assert storage_status_tone(3) == "warning"
    assert storage_status_tone(2) == "critical"


def test_storage_health_counts():
    counts = storage_health_counts([1, 1, 0, 2, 3])
    assert counts == {"total": 5, "active": 2, "problems": 3}


def test_architecture_and_bios_maps():
    assert ARCHITECTURE_MAP[1] == "x86_64"
    assert ARCHITECTURE_MAP[0] == "undefined"
    assert BIOS_TYPE_MAP[3] == "Q35 OVMF"


def test_audit_severity_tones_and_labels():
    from core.constants import (
        AUDIT_SEVERITY_MAP,
        audit_severity_label,
        audit_severity_tone,
    )

    assert AUDIT_SEVERITY_MAP[0] == "Normal"
    assert AUDIT_SEVERITY_MAP[1] == "Warning"
    assert AUDIT_SEVERITY_MAP[2] == "Error"
    assert AUDIT_SEVERITY_MAP[3] == "Alert"
    assert audit_severity_tone(0) == "neutral"
    assert audit_severity_tone(1) == "warning"
    assert audit_severity_tone(2) == "critical"
    assert audit_severity_tone(3) == "critical"
    assert audit_severity_label(4) == "Code 4"
    assert audit_severity_label(10) == "Code 10"


def test_async_task_status_map():
    from core.constants import (
        ACTION_TYPE_MAP,
        ASYNC_TASK_RESULT_MAP,
        ASYNC_TASK_STATUS_MAP,
        action_type_label,
        async_task_result_label,
        async_task_status_label,
    )

    assert ASYNC_TASK_STATUS_MAP[1] == "init"
    assert ASYNC_TASK_STATUS_MAP[2] == "running"
    assert ASYNC_TASK_STATUS_MAP[3] == "finished"
    assert async_task_status_label(99) == "Code 99"
    assert ASYNC_TASK_RESULT_MAP[0] == "success"
    assert async_task_result_label(1) == "failure"
    assert ACTION_TYPE_MAP[261] == "ConvertDisk"
    assert action_type_label(261) == "ConvertDisk"


def test_vdc_object_type_disk():
    from core.constants import vdc_object_type_label

    assert vdc_object_type_label(19) == "диск"
    assert vdc_object_type_label(5) == "ВМ"
    assert vdc_object_type_label(99) == "тип 99"


def test_async_task_buckets_are_exclusive():
    from core.constants import (
        async_task_bucket_code,
        async_task_health_counts,
        async_task_is_error,
        async_task_is_finished,
        async_task_is_running,
    )

    assert async_task_is_error(3, 1) is True
    assert async_task_is_finished(3, 1) is False
    assert async_task_is_running(2, 0) is True
    assert async_task_is_finished(3, 0) is True
    assert async_task_is_error(0, 0) is True
    assert async_task_bucket_code(3, 0) == 0
    assert async_task_bucket_code(2, 0) == 1
    assert async_task_bucket_code(3, 1) == 2
    counts = async_task_health_counts([(2, 0), (3, 0), (3, 1), (0, 0)])
    assert counts == {"total": 4, "running": 1, "finished": 1, "errors": 2}


def test_audit_health_counts_normal_only_in_total():
    from core.constants import audit_health_counts

    counts = audit_health_counts([0, 0, 1, 2, 3])
    assert counts["total"] == 5
    assert counts["warning"] == 1
    assert counts["errors"] == 2

"""Юнит-тесты Disk-Inspector без БД."""

from datetime import datetime

from disks.disks_inspector_sql import format_disk_report

PARENT = "aaaaaaaa-1111-2222-3333-444444444444"
CHILD = "bbbbbbbb-1111-2222-3333-444444444444"
DISK_ID = "cccccccc-1111-2222-3333-444444444444"
VM_A = "11111111-aaaa-bbbb-cccc-0000000000aa"
VM_B = "22222222-aaaa-bbbb-cccc-0000000000bb"
SNAP_ID = "d4e5f6a7-aaaa-bbbb-cccc-777777777777"


def _payload(**overrides):
    data = {
        "generated_at": "28.08.2026 23:20:00",
        "selected": {
            "image_guid": CHILD,
            "disk_id": DISK_ID,
            "disk_alias": "os",
            "shareable": False,
            "wipe_after_delete": True,
            "disk_content_type": 0,
            "imagestatus": 1,
            "virt_size": 10 * 1024**3,
            "actual_size": 3 * 1024**3,
            "active": True,
            "creation_date": datetime(2025, 8, 20, 5, 51, 0),
            "parentid": PARENT,
            "volume_type": 2,
            "volume_format": 4,
            "snapshot_id": SNAP_ID,
            "snap_name": "Active VM",
            "storage_name": "Dat6_SSD, Dat6_SSD_copy",
        },
        "attachments": [
            {
                "vm_id": VM_A,
                "vm_name": "web-01",
                "vm_status_code": 1,
                "is_plugged": True,
                "is_boot": True,
                "disk_interface": "VirtIO",
            },
            {
                "vm_id": VM_B,
                "vm_name": "web-02",
                "vm_status_code": 0,
                "is_plugged": False,
                "is_boot": False,
                "disk_interface": "VirtIO",
            },
        ],
        "layers": [
            {
                "disk_alias": "os",
                "image_guid": PARENT,
                "parentid": None,
                "active": False,
                "imagestatus": 1,
                "volume_type": 2,
                "volume_format": 4,
                "vm_snapshot_id": SNAP_ID,
                "size": 10 * 1024**3,
                "actual_size": 8 * 1024**3,
            },
            {
                "disk_alias": "os",
                "image_guid": CHILD,
                "parentid": PARENT,
                "active": True,
                "imagestatus": 1,
                "volume_type": 2,
                "volume_format": 4,
                "vm_snapshot_id": SNAP_ID,
                "size": 10 * 1024**3,
                "actual_size": 3 * 1024**3,
            },
        ],
        "tasks": [],
        "section_errors": {},
    }
    data.update(overrides)
    return data


def test_selected_layer_full_uuid_in_header():
    text = format_disk_report(_payload())
    assert CHILD in text
    assert DISK_ID in text
    assert "DISK-Inspector" in text
    assert "28.08.2026 23:20:00" in text
    assert "Dat6_SSD, Dat6_SSD_copy" in text
    assert SNAP_ID in text
    header = text.split("ДИСК")[0]
    assert CHILD in header


def test_layers_parent_then_child_marks_selected():
    text = format_disk_report(_payload())
    layers = text.split("СЛОИ")[1].split("ЗАДАЧИ")[0]
    assert layers.find(PARENT) < layers.find(CHILD)
    selected_line = [line for line in layers.splitlines() if CHILD in line][0]
    assert "← выбран" in selected_line
    parent_line = [line for line in layers.splitlines() if PARENT in line][0]
    assert "← выбран" not in parent_line


def test_two_vm_attachments():
    text = format_disk_report(_payload())
    binds = text.split("ПРИВЯЗКИ")[1].split("СЛОИ")[0]
    assert VM_A in binds
    assert VM_B in binds
    assert "web-01" in binds
    assert "web-02" in binds
    assert "не привязан" not in binds


def test_unknown_image_status_code():
    payload = _payload()
    payload["selected"]["imagestatus"] = 99
    text = format_disk_report(payload)
    header = text.split("ДИСК")[0]
    assert "Code 99" in header


def test_empty_attachments_and_layers():
    text = format_disk_report(_payload(attachments=[], layers=[], tasks=[]))
    assert "не привязан" in text
    assert "нет слоёв" in text
    assert "нет" in text.split("ЗАДАЧИ")[1]


def test_no_problems_section():
    text = format_disk_report(_payload())
    assert "ПРОБЛЕМЫ" not in text
    assert "ДИАГНОСТИКА" not in text
    assert "критичных проблем" not in text

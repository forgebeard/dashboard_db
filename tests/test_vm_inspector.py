"""Юнит-тесты VM Inspector без БД."""

from datetime import datetime

from vms.vm_inspector_sql import (
    NIL_UUID,
    format_vm_report,
    guest_os_label,
    layer_note,
    layer_snap_label,
    order_layers_by_parent,
    snapshot_type_label,
)

PARENT = "aaaaaaaa-1111-2222-3333-444444444444"
CHILD = "bbbbbbbb-1111-2222-3333-444444444444"
DISK_ID = "dddddddd-1111-2222-3333-444444444444"
SNAP_ID = "ssssssss-1111-2222-3333-444444444444"


def _payload(**overrides):
    data = {
        "generated_at": "28.08.2026 16:00:00",
        "header": {
            "name": "Test1",
            "id": "vm-uuid",
            "description": "подпись из vm_static",
            "comment": None,
            "os": "Other Linux (kernel 4.x)",
            "guest_os": "CentOS 7",
            "template": "Blank",
            "bios": "Q35 SeaBIOS",
            "cluster": "Default",
            "dc": "Default",
            "host": "host-01",
            "created": "01.01.2024 12:00",
            "updated": "15.08.2026 09:30",
        },
        "metrics": {
            "status": "Up",
            "uptime": "2д 3ч 10м",
            "cpu": "1 сокета × 2 ядер    потоки: 1",
            "ram": "4.0 ГБ",
            "vm_ip": "10.0.0.8",
            "qemu_agent": "есть",
            "ovirt_agent": "нет",
        },
        "disks": [],
        "layers": [],
        "snapshots": [],
        "networks": [],
        "events": [],
        "section_errors": {},
    }
    data.update(overrides)
    return data


def test_header_has_description_os_dates():
    text = format_vm_report(_payload())
    assert "VM-Inspector" in text
    assert "СВЕДЕНИЯ О ВМ" in text
    assert "подпись из vm_static" in text
    assert "Other Linux (kernel 4.x)" in text
    assert "CentOS 7" in text
    assert "01.01.2024 12:00" in text
    assert "15.08.2026 09:30" in text
    assert "Комментарий" not in text
    assert "ОСНОВНАЯ ИНФОРМАЦИЯ" not in text
    assert "ДИАГНОСТИКА" not in text
    assert "Критичных проблем не обнаружено" not in text


def test_empty_disks_and_snapshots():
    text = format_vm_report(_payload())
    assert "нет дисков" in text
    assert "нет слоёв" in text
    assert "нет снапшотов" in text
    assert "нет интерфейсов" in text
    assert "нет событий" in text


def test_disk_card_prints_full_uuids():
    text = format_vm_report(
        _payload(
            disks=[
                {
                    "disk_alias": "os-disk",
                    "disk_id": DISK_ID,
                    "is_boot": True,
                    "disk_interface": "virtio",
                    "is_plugged": True,
                    "virt_bytes": 40 * 1024**3,
                    "imagestatus": 1,
                    "storage_name": "data1",
                    "active_image": PARENT,
                }
            ]
        )
    )
    assert DISK_ID in text
    assert PARENT in text
    assert "имя:" in text
    assert "Активный слой" in text
    assert "Вирт. размер" in text
    assert "Boot" in text
    assert "Подключён" in text
    assert "Статус" in text
    assert "os-disk  boot  virtio" not in text
    disk_block = text.split("СЛОИ")[0]
    active_line = [line for line in disk_block.splitlines() if "Активный слой" in line][0]
    assert "OK" not in active_line


def test_layer_without_snapshot_uses_dash():
    assert layer_snap_label({"vm_snapshot_id": None, "snap_desc": None}) == "—"
    assert layer_snap_label({"vm_snapshot_id": "", "snap_desc": "old"}) == "—"
    assert layer_note({"vm_snapshot_id": None}) is None
    text = format_vm_report(
        _payload(
            layers=[
                {
                    "disk_alias": "os-disk",
                    "image_guid": PARENT,
                    "parentid": NIL_UUID,
                    "active": True,
                    "imagestatus": 1,
                    "volume_type": 2,
                    "volume_format": 4,
                    "vm_snapshot_id": None,
                    "snap_desc": None,
                    "it_guid": NIL_UUID,
                    "actual_size": 8 * 1024**3,
                    "_create_date": datetime(2024, 6, 1, 9, 0, 1),
                    "creation_date": datetime(2024, 6, 1, 10, 0, 2),
                    "_update_date": datetime(2024, 6, 1, 11, 0, 3),
                }
            ]
        )
    )
    assert PARENT in text
    assert NIL_UUID in text
    assert "image_guid:" in text
    assert "parentid:" in text
    assert "_create_date:" in text
    assert "creation_date:" in text
    assert "_update_date:" in text
    assert "01.06.2024 09:00:01" in text
    assert "01.06.2024 10:00:02" in text
    assert "01.06.2024 11:00:03" in text
    assert "состояние" in text
    assert "снапшот:" in text
    assert "заметка" not in text
    assert "пользовательский снимок" not in text
    assert "ДИСКИ И СНАПШОТЫ" not in text


def test_parent_chain_ignores_dates():
    child_first = [
        {
            "disk_alias": "os-disk",
            "image_guid": CHILD,
            "parentid": PARENT,
            "active": True,
            "creation_date": datetime(2020, 1, 1),
        },
        {
            "disk_alias": "os-disk",
            "image_guid": PARENT,
            "parentid": None,
            "active": False,
            "creation_date": datetime(2025, 1, 1),
        },
    ]
    ordered = order_layers_by_parent(child_first)
    assert [row["image_guid"] for row in ordered] == [PARENT, CHILD]
    text = format_vm_report(_payload(layers=child_first))
    assert text.find(PARENT) < text.find(CHILD)
    assert PARENT in text
    assert CHILD in text


def test_snapshot_with_zero_layers_is_visible():
    assert snapshot_type_label("ACTIVE") == "ACTIVE"
    text = format_vm_report(
        _payload(
            snapshots=[
                {
                    "snapshot_id": SNAP_ID,
                    "snapshot_type": "ACTIVE",
                    "status": "OK",
                    "description": "Active VM",
                    "creation_date": datetime(2024, 7, 1, 8, 0),
                    "memory_dump_disk_id": None,
                    "memory_metadata_disk_id": None,
                    "layer_count": 0,
                }
            ]
        )
    )
    assert SNAP_ID in text
    assert "snapshot_id:" in text
    assert "Active VM" in text
    assert "слои:" in text
    assert "слоёв 0" not in text
    assert "память" not in text
    assert "пользовательский снимок" not in text
    assert "нет снапшотов" not in text
    snap_block = text.split("СНАПШОТЫ")[1]
    layers_line = [line for line in snap_block.splitlines() if "слои:" in line][0]
    assert layers_line.strip().endswith("—")


def test_snapshot_layers_one_line_or_many():
    extra = "cccccccc-1111-2222-3333-444444444444"
    one = format_vm_report(
        _payload(
            layers=[{"image_guid": PARENT, "vm_snapshot_id": SNAP_ID}],
            snapshots=[{"snapshot_id": SNAP_ID, "snapshot_type": "REGULAR"}],
        )
    )
    one_line = [line for line in one.split("СНАПШОТЫ")[1].splitlines() if "слои:" in line][0]
    assert PARENT in one_line
    many = format_vm_report(
        _payload(
            layers=[
                {"image_guid": PARENT, "vm_snapshot_id": SNAP_ID},
                {"image_guid": extra, "vm_snapshot_id": SNAP_ID},
            ],
            snapshots=[{"snapshot_id": SNAP_ID, "snapshot_type": "REGULAR"}],
        )
    )
    many_line = [line for line in many.split("СНАПШОТЫ")[1].splitlines() if "слои:" in line][0]
    assert PARENT not in many_line
    assert extra not in many_line
    assert PARENT in many
    assert extra in many


def test_guest_os_prefers_distribution():
    assert guest_os_label(
        {"guestos_distribution": "RHEL", "guestos_version": "8.6", "guest_os": "other"}
    ) == "RHEL 8.6"
    assert guest_os_label({"guest_os": "Windows"}) == "Windows"
    assert guest_os_label({}) is None


def test_network_ip_on_same_line():
    text = format_vm_report(
        _payload(
            networks=[
                {
                    "name": "nic1",
                    "mac_addr": "aa:bb:cc:dd:ee:ff",
                    "net_name": "ovirtmgmt",
                    "ipv4": "10.1.2.3",
                }
            ]
        )
    )
    assert "10.1.2.3" in text
    assert "ovirtmgmt" in text
    assert "IP-адреса (Guest Agent)" not in text

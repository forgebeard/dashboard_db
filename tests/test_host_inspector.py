"""Юнит-тесты Host Inspector без БД."""

from datetime import datetime

from hosts.host_inspector_sql import (
    audit_object,
    audit_type_label,
    compact_audit_line,
    format_host_report,
    group_host_interfaces,
)


def _iface(**kwargs):
    row = {
        "name": "eth0",
        "mac_addr": None,
        "addr": None,
        "mtu": 1500,
        "speed": None,
        "is_bond": False,
        "bond_name": None,
        "vlan_id": None,
    }
    row.update(kwargs)
    return row


def test_group_vlans_collapse_under_bond():
    grouped = group_host_interfaces(
        [
            _iface(name="bond0", is_bond=True, mac_addr="aa:aa", speed=30000),
            _iface(name="enp0", bond_name="bond0", speed=10000, mac_addr="aa:aa"),
            _iface(name="enp1", bond_name="bond0", speed=10000, mac_addr="bb:bb"),
            _iface(name="bond0.15", bond_name="bond0", vlan_id=15, speed=30000),
            _iface(name="bond0.29", bond_name="bond0", vlan_id=29, speed=30000),
            _iface(name="eno1", mac_addr="cc:cc"),
        ]
    )
    assert [b["name"] for b in grouped["bonds"]] == ["bond0"]
    ports = [p["name"] for p in grouped["slaves_by_bond"]["bond0"]]
    assert ports == ["enp0", "enp1"]
    assert grouped["vlans_by_parent"]["bond0"] == [15, 29]
    assert [o["name"] for o in grouped["others"]] == ["eno1"]


def test_format_report_vlan_and_ports():
    text = format_host_report(
        {
            "generated_at": "27.08.2026 10:33:32",
            "header": {
                "name": "host-01",
                "id": "abc",
                "fqdn": "host-01.example",
                "cluster": "Default",
                "dc": "Default",
                "created": "01.01.2024 12:00",
                "updated": "15.08.2026 09:30",
            },
            "metrics": {
                "status": "Up",
                "kdump": "Disabled",
                "spm": "нет",
                "cpu": "2 сокета × 56 ядер",
                "cpu_model": "Intel Xeon Gold 6248R",
                "ram": "1511.5 ГБ физ.",
                "vm_active": 45,
            },
            "versions": {
                "os": "EL",
                "kernel": "5.15",
                "vdsm": "4.40",
                "libvirt": "10.10",
                "kvm": "9.1",
            },
            "networks": [
                _iface(name="bond0", is_bond=True, mac_addr="3c:fd:fe:97:10:c0", speed=30000),
                _iface(
                    name="enp49s0f0",
                    bond_name="bond0",
                    speed=10000,
                    mac_addr="3c:fd:fe:97:10:c0",
                ),
                _iface(name="bond0.15", bond_name="bond0", vlan_id=15, speed=30000),
                _iface(name="bond0.41", bond_name="bond0", vlan_id=41, speed=30000),
                _iface(
                    name="enp49s0f2",
                    addr="10.195.10.251",
                    speed=10000,
                    mac_addr="3c:fd:fe:97:10:c2",
                ),
            ],
            "events": [],
        }
    )
    assert "СВЕДЕНИЯ О ХОСТЕ" in text
    assert "Создан" in text
    assert "01.01.2024 12:00" in text
    assert "Обновлён" in text
    assert "Intel Xeon Gold 6248R" in text
    assert "порты:" in text
    assert "enp49s0f0 (10G)" in text
    assert "VLAN:" in text
    assert "15 41" in text
    assert text.count("bond0.15") == 0
    assert "10.195.10.251" in text
    assert "Host-Inspector v2.0" not in text
    assert "ОСНОВНАЯ ИНФОРМАЦИЯ" not in text
    assert "tsk1-fs03_1" not in text
    assert "ВИРТУАЛЬНЫЕ МАШИНЫ" not in text
    assert "ХРАНИЛИЩА" not in text
    assert "ПРОВЕРКИ" not in text
    assert "Критичных проблем нет" not in text


def test_audit_one_line_no_user_repeat():
    event = {
        "log_time": datetime(2026, 5, 21, 16, 49, 25),
        "log_type_name": "VM_CONSOLE_DISCONNECTED",
        "user_name": "admin@internal-authz",
        "message": "User admin@internal-authz got disconnected from VM tsk1-fs03_1.",
    }
    assert audit_type_label("VM_CONSOLE_DISCONNECTED") == "console disconnected"
    assert audit_object("VM_CONSOLE_DISCONNECTED", event["message"]) == "tsk1-fs03_1"
    line = compact_audit_line(event)
    assert "\n" not in line
    assert "console disconnected" in line
    assert "tsk1-fs03_1" in line
    assert line.count("admin@internal-authz") == 1
    assert "VM_CONSOLE_DISCONNECTED" not in line

    attach = {
        "log_time": datetime(2026, 5, 21, 15, 50, 48),
        "log_type_name": "USER_ATTACH_DISK_TO_VM",
        "user_name": "admin@internal-authz",
        "message": (
            "Disk tsk1-fs03_1_Disk2_TMP_EXCH was successfully attached "
            "to VM tsk1-exchmb01 by admin@internal-authz."
        ),
    }
    obj = audit_object(attach["log_type_name"], attach["message"])
    assert obj == "tsk1-fs03_1_Disk2_TMP_EXCH -> tsk1-exchmb01"
    text = format_host_report(
        {
            "generated_at": "01.01.2026 00:00:00",
            "header": {"name": "h1"},
            "metrics": {"vm_active": 2},
            "versions": {},
            "networks": [],
            "events": [event, attach],
        }
    )
    assert "ЖУРНАЛ СОБЫТИЙ" in text
    assert "User admin@internal-authz got disconnected" not in text


def test_fetch_host_networks_retries_on_missing_column():
    from unittest.mock import MagicMock

    from core.exceptions import DataLoadError
    from hosts.host_inspector_sql import _fetch_host_networks

    insp = MagicMock()
    insp.fetch_all.side_effect = [
        DataLoadError('column "network_name" does not exist'),
        [{"name": "eth0"}],
    ]
    rows = _fetch_host_networks(insp, "guid")
    assert rows == [{"name": "eth0"}]
    assert insp.fetch_all.call_count == 2


def test_fetch_host_networks_does_not_retry_timeout():
    from unittest.mock import MagicMock

    import pytest

    from core.exceptions import DataLoadError
    from hosts.host_inspector_sql import _fetch_host_networks

    insp = MagicMock()
    insp.fetch_all.side_effect = DataLoadError("statement timeout")
    with pytest.raises(DataLoadError, match="statement timeout"):
        _fetch_host_networks(insp, "guid")
    assert insp.fetch_all.call_count == 1

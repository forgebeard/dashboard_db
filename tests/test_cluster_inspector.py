"""Юнит-тесты Cluster Inspector без БД."""

from clusters.cluster_inspector_sql import format_cluster_report
from core.constants import ARCHITECTURE_MAP, BIOS_TYPE_MAP


def _payload(**overrides):
    data = {
        "generated_at": "28.08.2026 18:30:00",
        "header": {
            "name": "IS-CL",
            "id": "39999742-57d1-435f-9d9b-fc29d3464b7f",
            "dc": "IS-DC",
            "compat": "4.6",
            "cpu": "Secure Intel Cascadelake Server Family",
            "architecture": ARCHITECTURE_MAP[1],
            "machine": "pc-i440fx-2.12;pc-q35-4.1",
            "bios": BIOS_TYPE_MAP[3],
            "mac_pool": "Default",
            "scheduler": "—",
        },
        "resources": {
            "vms": "115 Up / 129",
            "capacity": "6043.7 ГБ  /  192 ядер",
            "overcommit": "100%",
        },
        "policy": {
            "properties": [
                ("CpuOverCommitDurationMinutes", "2"),
                ("HighUtilization", "80"),
            ],
            "migrate_on_error": "Migrate",
            "memory": "вкл / вкл",
            "ha_reservation": "выкл",
            "fencing": "вкл",
            "fencing_extra": [],
        },
        "hosts": [
            {"name": "host-a", "status": "Up"},
            {"name": "host-b", "status": "Up"},
        ],
        "affinity": [],
        "section_errors": {},
    }
    data.update(overrides)
    return data


def test_format_cluster_report_layout():
    text = format_cluster_report(_payload())
    assert "Cluster-Inspector" in text
    assert "СВЕДЕНИЯ О КЛАСТЕРЕ" in text
    assert "РЕСУРСЫ" in text
    assert "ПОЛИТИКА" in text
    assert "ХОСТЫ" in text
    assert "СЕТИ" not in text
    assert "все Up" not in text
    assert "АФФИННОСТЬ" not in text
    assert "x86_64" in text
    assert "Q35 OVMF" in text
    assert "Планировщик:" in text
    assert "HighUtilization" in text
    assert "host-a" in text and "Up" in text
    assert "115 Up / 129" in text


def test_format_cluster_empty_hosts():
    text = format_cluster_report(_payload(hosts=[]))
    assert "нет хостов" in text


def test_format_cluster_affinity_names():
    text = format_cluster_report(
        _payload(
            affinity=[
                {
                    "name": "web",
                    "vm_rule": "Positive (Soft)",
                    "host_rule": "Negative",
                    "members": ["vm-one", "host-a"],
                }
            ]
        )
    )
    assert "АФФИННОСТЬ" in text
    assert "web" in text
    assert "vm-one" in text
    assert "host-a" in text

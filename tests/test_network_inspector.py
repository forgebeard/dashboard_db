"""Юнит-тесты Network-Inspector без БД."""

from networks.network_inspector_sql import (
    HOST_ATTACHMENTS_SQL,
    NETWORK_VMS_SQL,
    VM_LIST_LIMIT,
    format_network_report,
)

NET_ID = "aaaaaaaa-1111-2222-3333-444444444444"
CLUSTER_A = "bbbbbbbb-1111-2222-3333-444444444444"
CLUSTER_B = "cccccccc-1111-2222-3333-444444444444"
HOST_ID = "dddddddd-1111-2222-3333-444444444444"
VM_A = "11111111-aaaa-bbbb-cccc-0000000000aa"
VM_B = "22222222-aaaa-bbbb-cccc-0000000000bb"
PROFILE_ID = "eeeeeeee-1111-2222-3333-444444444444"


def _payload(**overrides):
    data = {
        "generated_at": "28.08.2026 23:40:00",
        "header": {
            "id": NET_ID,
            "name": "ovirtmgmt",
            "description": "mgmt",
            "vlan_id": None,
            "vm_network": True,
            "mtu": 1500,
            "stp": False,
            "label": None,
            "vdsm_name": "ovirtmgmt",
            "subnet": "255.255.255.0",
            "gateway": "192.168.1.1",
            "type": 1,
            "dc_name": "Default",
        },
        "clusters": [
            {
                "cluster_name": "Default",
                "cluster_id": CLUSTER_A,
                "status": 0,
                "is_display": True,
                "required": True,
                "management": True,
                "default_route": True,
                "migration": True,
                "is_gluster": False,
            },
            {
                "cluster_name": "Compute",
                "cluster_id": CLUSTER_B,
                "status": 1,
                "is_display": False,
                "required": False,
                "management": False,
                "default_route": False,
                "migration": False,
                "is_gluster": True,
            },
        ],
        "profiles": [
            {
                "id": PROFILE_ID,
                "name": "ovirtmgmt",
                "port_mirroring": False,
                "passthrough": False,
                "migratable": True,
                "filter_name": None,
                "qos_name": None,
            }
        ],
        "dns": [{"address": "8.8.8.8", "position": 0}],
        "hosts": [
            {
                "vds_name": "host-01",
                "vds_id": HOST_ID,
                "iface_name": "enp1s0",
                "vlan_id": None,
                "address": "192.168.1.10",
            }
        ],
        "vms": [
            {
                "vm_name": "web-01",
                "vm_id": VM_A,
                "mac_addr": "00:1a:4a:16:01:01",
                "profile_name": "ovirtmgmt",
            },
            {
                "vm_name": "web-02",
                "vm_id": VM_B,
                "mac_addr": "00:1a:4a:16:01:02",
                "profile_name": "ovirtmgmt",
            },
        ],
        "section_errors": {},
    }
    data.update(overrides)
    return data


def test_network_uuid_in_header():
    text = format_network_report(_payload())
    header = text.split("КЛАСТЕРЫ")[0]
    assert NET_ID in header
    assert "ovirtmgmt" in header
    assert "Network-Inspector" in text
    assert "28.08.2026 23:40:00" in header


def test_two_clusters_migration_gluster_flags():
    text = format_network_report(_payload())
    block = text.split("КЛАСТЕРЫ")[1].split("ПРОФИЛИ")[0]
    assert CLUSTER_A in block
    assert CLUSTER_B in block
    assert "Default" in block
    assert "Compute" in block
    assert "migration:" in block
    assert "gluster:" in block


def test_host_from_attachments_only():
    text = format_network_report(_payload())
    hosts = text.split("ХОСТЫ")[1].split("ВМ")[0]
    assert HOST_ID in hosts
    assert "host-01" in hosts
    assert "enp1s0" in hosts
    assert "192.168.1.10" in hosts
    assert "host-other" not in hosts


def test_two_vms_full_uuid():
    text = format_network_report(_payload())
    vms = text.split("\nВМ\n")[1]
    assert VM_A in vms
    assert VM_B in vms
    assert "web-01" in vms
    assert "web-02" in vms
    assert "показаны первые 50" not in text


def test_fifty_vms_caption():
    vms = [
        {
            "vm_name": f"vm-{i:02d}",
            "vm_id": f"{i:08x}-aaaa-bbbb-cccc-0000000000aa",
            "mac_addr": "00:1a:4a:16:01:01",
            "profile_name": "ovirtmgmt",
        }
        for i in range(VM_LIST_LIMIT)
    ]
    text = format_network_report(_payload(vms=vms))
    assert "показаны первые 50" in text.split("\nВМ\n")[1]


def test_vms_sql_limited_to_50():
    sql = " ".join(NETWORK_VMS_SQL.lower().split())
    assert sql.endswith("limit 50")


def test_unknown_type_and_cluster_status_codes():
    payload = _payload()
    payload["header"]["type"] = 99
    payload["clusters"][0]["status"] = 7
    text = format_network_report(payload)
    header = text.split("КЛАСТЕРЫ")[0]
    assert "Code 99" in header
    clusters = text.split("КЛАСТЕРЫ")[1].split("ПРОФИЛИ")[0]
    assert "Code 7" in clusters
    assert "Operational" in clusters
    assert "NonOperational" in format_network_report(_payload()).split("КЛАСТЕРЫ")[1].split("ПРОФИЛИ")[0]


def test_empty_sections():
    text = format_network_report(
        _payload(clusters=[], profiles=[], dns=[], hosts=[], vms=[])
    )
    assert "нет кластеров" in text
    assert "нет профилей" in text
    assert "нет DNS" in text
    assert "нет хостов" in text
    assert "нет ВМ" in text


def test_no_problems_or_emoji():
    text = format_network_report(_payload())
    assert "ПРОБЛЕМЫ" not in text
    assert "✅" not in text
    assert "❌" not in text


def test_host_sql_filters_by_network_id_not_vlan():
    sql = " ".join(HOST_ATTACHMENTS_SQL.lower().split())
    where = sql.split("where", 1)[1]
    assert "na.network_id" in where
    assert " or " not in where
    assert "vlan_id" not in where
    assert "vlan_id" in sql

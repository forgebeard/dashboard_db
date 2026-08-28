"""Юнит-тесты STORAGE-Inspector без БД."""

from core.constants import STORAGE_DOMAIN_STATUS_MAP
from storage.storage_inspector_sql import (
    collect_storage_issues,
    format_storage_report,
)


def _hosted_payload(**overrides):
    payload = {
        "generated_at": "28.08.2026 20:50:00",
        "header": {
            "name": "hosted_storage",
            "id": "d7ea352c-7032-4352-8fd6-bafad2fd9a53",
            "domain_type": "Master",
            "storage_type": "iSCSI",
            "storage_ref": "XCki3p-nsu3-Ky1s-qZlh-jjxq-wVL4-Ymcm21",
            "format": 5,
            "is_master": True,
            "is_he": True,
            "backup": False,
        },
        "shared_code": 1,
        "shared_status": "Active",
        "attachments": [
            {
                "dc_name": "IS-DC",
                "attach_code": 3,
                "attach_status": "Active",
                "dc_status": "Up",
                "spm_host": "is-node3.miac.local",
                "spm_code": 3,
                "spm_status": "Up",
            }
        ],
        "space": {
            "used": 79,
            "free": 220,
            "total": 299,
            "used_pct": 26.4,
            "free_pct": 73.6,
            "warning_free_pct": 10,
            "critical_free_pct": 5,
            "external_status": 0,
            "confirmed_available": None,
        },
        "connection_kind": "block",
        "luns": [
            {
                "lun_id": "36f82e3f10028d17bc9dda9f00000000a",
                "vendor_id": "HUAWEI",
                "product_id": "XSG1",
                "device_size": 300,
                "path_count": 2,
            }
        ],
        "portals": [
            {
                "connection": "10.92.54.134",
                "iqn": "iqn.2006-08.com.huawei:oceanstor:2100f82e3f28d17b::1020000:10.92.54.134",
                "port": 3260,
            }
        ],
        "file_connection": {},
        "images": [{"status": 1, "count": 6}],
        "vms": [{"entity_type": "VM", "status": 1, "count": 1}],
        "bad_images": [],
    }
    payload.update(overrides)
    return payload


def test_format_hosted_storage_dump():
    text = format_storage_report(_hosted_payload())
    assert "СВЕДЕНИЯ О ДОМЕНЕ" in text
    assert "hosted_storage" in text
    assert "Master" in text
    assert "Hosted Engine" in text
    assert "299 ГБ" in text
    assert "HUAWEI" in text
    assert "пути 2" in text
    assert "10.92.54.134" in text
    assert "Образы: OK 6" in text
    assert "VM: Up × 1" in text
    assert "критичных проблем нет" in text
    assert "PROBLEM" not in text
    assert "Mixed" not in text
    assert collect_storage_issues(_hosted_payload()) == []


def test_glance_has_no_lun_section():
    text = format_storage_report(
        {
            "generated_at": "28.08.2026 20:50:00",
            "header": {
                "name": "ovirt-image-repository",
                "id": "072fbaa1-08f3-4a40-9f34-a5ca22dd1d74",
                "domain_type": "Image",
                "storage_type": "Glance",
                "storage_ref": "ceab03af-7220-4d42-8f5c-9b557f5d29af",
                "format": None,
                "is_master": False,
                "is_he": False,
                "backup": False,
            },
            "shared_code": 1,
            "shared_status": "Active",
            "attachments": [],
            "space": {
                "used": 0,
                "free": 0,
                "total": 0,
                "used_pct": 0,
                "free_pct": 0,
                "warning_free_pct": 10,
                "critical_free_pct": 5,
                "external_status": 0,
            },
            "connection_kind": "glance",
            "luns": [{"lun_id": "should-not-print", "vendor_id": "X"}],
            "portals": [],
            "images": [],
            "vms": [],
            "bad_images": [],
        }
    )
    assert "LUN" not in text
    assert "Glance" in text
    assert "ceab03af-7220-4d42-8f5c-9b557f5d29af" in text
    assert "ovirt-image-repository" in text


def test_inactive_attach_is_issue():
    payload = _hosted_payload()
    payload["attachments"] = [
        {
            "dc_name": "IS-DC",
            "attach_code": 4,
            "attach_status": STORAGE_DOMAIN_STATUS_MAP[4],
            "dc_status": "Up",
            "spm_host": "is-node3.miac.local",
            "spm_code": 3,
            "spm_status": "Up",
        }
    ]
    issues = collect_storage_issues(payload)
    assert any("Inactive" in item for item in issues)
    text = format_storage_report(payload)
    assert "привязка IS-DC: Inactive" in text
    assert "критичных проблем нет" not in text


def test_mixed_shared_is_not_labeled_problem():
    payload = _hosted_payload(shared_code=3, shared_status="Mixed")
    issues = collect_storage_issues(payload)
    assert issues == ["shared status: Mixed"]
    text = format_storage_report(payload)
    assert "Mixed" in text
    assert "PROBLEM" not in text


def test_low_free_space_uses_domain_thresholds():
    payload = _hosted_payload()
    payload["space"] = {
        **payload["space"],
        "used": 290,
        "free": 9,
        "total": 299,
        "used_pct": 97.0,
        "free_pct": 3.0,
        "warning_free_pct": 10,
        "critical_free_pct": 5,
    }
    issues = collect_storage_issues(payload)
    assert any("critical" in item for item in issues)

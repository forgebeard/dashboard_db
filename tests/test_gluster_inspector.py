"""Юнит-тесты Gluster Volume-Inspector без БД."""

from datetime import datetime

from gluster.gluster_inspector_sql import format_gluster_report

VOL_ID = "aaaaaaaa-1111-2222-3333-444444444444"
BRICK_A = "bbbbbbbb-1111-2222-3333-444444444444"
BRICK_B = "cccccccc-1111-2222-3333-444444444444"


def _payload(**overrides):
    data = {
        "generated_at": "28.08.2026 23:50:00",
        "header": {
            "id": VOL_ID,
            "vol_name": "gv0",
            "cluster_name": "Gluster",
            "vol_type": "Replicate",
            "status": "Started",
            "replica_count": 3,
            "disperse_count": 0,
            "stripe_count": 0,
            "snapshot_count": 1,
            "total_space": 100 * 1024**3,
            "used_space": 40 * 1024**3,
            "free_space": 60 * 1024**3,
        },
        "bricks": [
            {
                "id": BRICK_A,
                "brick_dir": "/gluster/brick1",
                "vds_name": "gfs-01",
                "interface_address": "10.0.0.1",
                "brick_status": "Started",
                "is_arbiter": False,
                "brick_used": 20 * 1024**3,
                "brick_total": 50 * 1024**3,
            },
            {
                "id": BRICK_B,
                "brick_dir": "/gluster/brick2",
                "vds_name": "gfs-02",
                "interface_address": "10.0.0.2",
                "brick_status": "Started",
                "is_arbiter": True,
                "brick_used": 1 * 1024**3,
                "brick_total": 50 * 1024**3,
            },
        ],
        "options": [{"option_key": "performance.cache-size", "option_val": "256MB"}],
        "georep": [],
        "snapshots": [
            {
                "snapshot_name": "snap1",
                "description": "weekly",
                "status": "Started",
                "_create_date": datetime(2025, 8, 1, 12, 0, 0),
            }
        ],
        "section_errors": {},
    }
    data.update(overrides)
    return data


def test_volume_uuid_in_header():
    text = format_gluster_report(_payload())
    header = text.split("КИРПИЧИ")[0]
    assert VOL_ID in header
    assert "gv0" in header
    assert "Gluster-Inspector" in text
    assert "Started" in header
    assert "Code " not in header


def test_replica_disperse_stripe_in_header():
    text = format_gluster_report(_payload())
    header = text.split("КИРПИЧИ")[0]
    assert "replica:" in header
    assert "3" in header
    assert "disperse:" in header
    assert "stripe:" in header


def test_two_bricks_uuid_and_arbiter():
    text = format_gluster_report(_payload())
    bricks = text.split("КИРПИЧИ")[1].split("ОПЦИИ")[0]
    assert BRICK_A in bricks
    assert BRICK_B in bricks
    assert "gfs-01" in bricks
    assert "gfs-02" in bricks
    assert "/gluster/brick1" in bricks
    assert "arbiter:" in bricks
    assert "да" in bricks
    assert "нет" in bricks


def test_empty_sections():
    text = format_gluster_report(
        _payload(bricks=[], options=[], georep=[], snapshots=[])
    )
    assert "нет кирпичей" in text
    assert "нет опций" in text
    assert "нет geo" in text
    assert "нет снапшотов" in text


def test_no_html_escape_or_problems():
    text = format_gluster_report(
        _payload(options=[{"option_key": "auth.allow", "option_val": "a & b"}])
    )
    assert "a & b" in text
    assert "&amp;" not in text
    assert "ПРОБЛЕМЫ" not in text
    assert "highlight" not in text.lower()

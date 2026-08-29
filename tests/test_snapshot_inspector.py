"""Юнит-тесты Snapshot-Inspector без БД."""

from datetime import datetime

from snapshots.snapshot_inspector_sql import format_snapshot_report

PARENT = "aaaaaaaa-1111-2222-3333-444444444444"
CHILD = "bbbbbbbb-1111-2222-3333-444444444444"
SNAP_OLD = "11111111-aaaa-bbbb-cccc-0000000000aa"
SNAP_SEL = "c3d4e5f6-1111-2222-3333-444444444444"
SNAP_ACT = "d4e5f6a7-aaaa-bbbb-cccc-777777777777"
DUMP_ID = "dddddddd-1111-2222-3333-444444444444"
CP_ID = "cp-aaaa-bbbb-cccc-999999999999"


def _payload(**overrides):
    data = {
        "generated_at": "28.08.2026 22:40:00",
        "header": {
            "name": "tsk1-aisrepo01",
            "id": "7c1a9e20-aaaa-bbbb-cccc-111111111111",
            "cluster": "Default",
            "dc": "Default",
        },
        "selected": {
            "snapshot_id": SNAP_SEL,
            "snapshot_type": "REGULAR",
            "status": "OK",
            "description": "Чистая система",
            "creation_date": datetime(2025, 8, 20, 5, 51, 0),
            "memory_dump_disk_id": DUMP_ID,
            "memory_dump_alias": "aisrepo01_memory_dump",
            "memory_metadata_disk_id": None,
            "memory_metadata_alias": None,
            "vm_configuration_broken": False,
        },
        "snapshots": [
            {
                "snapshot_id": SNAP_OLD,
                "snapshot_type": "REGULAR",
                "description": "weekly",
                "creation_date": datetime(2025, 3, 1, 3, 0, 0),
                "layer_count": 1,
            },
            {
                "snapshot_id": SNAP_SEL,
                "snapshot_type": "REGULAR",
                "description": "Чистая система",
                "creation_date": datetime(2025, 8, 20, 5, 51, 0),
                "layer_count": 1,
            },
            {
                "snapshot_id": SNAP_ACT,
                "snapshot_type": "ACTIVE",
                "description": "Active VM",
                "creation_date": datetime(2025, 11, 22, 4, 34, 0),
                "layer_count": 1,
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
                "vm_snapshot_id": SNAP_OLD,
                "size": 10 * 1024**3,
                "actual_size": 8 * 1024**3,
                "storage_name": "Dat6_SSD",
            },
            {
                "disk_alias": "os",
                "image_guid": CHILD,
                "parentid": PARENT,
                "active": False,
                "imagestatus": 1,
                "volume_type": 2,
                "volume_format": 4,
                "vm_snapshot_id": SNAP_SEL,
                "size": 12 * 1024**3,
                "actual_size": 4 * 1024**3,
                "storage_name": "Dat6_SSD",
            },
        ],
        "checkpoints": [],
        "section_errors": {},
    }
    data.update(overrides)
    return data


def test_selected_snapshot_full_uuid_in_header():
    text = format_snapshot_report(_payload())
    assert "Snapshot-Inspector" in text
    assert "tsk1-aisrepo01" in text
    assert SNAP_SEL in text
    assert "7c1a9e20-aaaa-bbbb-cccc-111111111111" in text
    assert "Чистая система" in text
    assert "REGULAR" in text
    assert DUMP_ID in text
    assert "aisrepo01_memory_dump" in text
    assert CHILD in text
    assert "ПРОБЛЕМЫ" not in text
    assert "критичных проблем" not in text


def test_chain_marks_selected_snapshot():
    text = format_snapshot_report(_payload())
    chain = text.split("ЦЕПОЧКА ВМ")[1].split("СЛОИ ВМ")[0]
    assert "►" in chain
    selected_line = [line for line in chain.splitlines() if SNAP_SEL in line][0]
    assert "►" in selected_line
    old_line = [line for line in chain.splitlines() if SNAP_OLD in line][0]
    assert "►" not in old_line


def test_vm_layers_parent_and_selected_mark():
    text = format_snapshot_report(_payload())
    vm_layers = text.split("СЛОИ ВМ")[1]
    assert PARENT in vm_layers
    assert "parentid:" in vm_layers
    assert "← выбран" in vm_layers
    assert vm_layers.find(PARENT) < vm_layers.find(CHILD)


def test_empty_checkpoints():
    text = format_snapshot_report(_payload())
    assert "нет чекпоинтов" in text
    assert CP_ID not in text


def test_checkpoint_full_uuid():
    text = format_snapshot_report(
        _payload(
            checkpoints=[
                {
                    "checkpoint_id": CP_ID,
                    "parent_id": None,
                    "_create_date": datetime(2025, 8, 21, 1, 10, 0),
                    "state": "Done",
                    "description": "backup-job",
                }
            ]
        )
    )
    assert CP_ID in text
    assert "нет чекпоинтов" not in text
    assert "Done" in text
    assert "parent_id:" in text


def test_fetch_snapshots_retries_on_missing_column():
    from unittest.mock import MagicMock

    from core.exceptions import DataLoadError
    from snapshots.snapshot_inspector_sql import _fetch_snapshots

    insp = MagicMock()
    insp.fetch_all.side_effect = [
        DataLoadError('column "vm_configuration_broken" does not exist'),
        [{"snapshot_id": "1"}],
    ]
    rows = _fetch_snapshots(insp, "guid")
    assert rows == [{"snapshot_id": "1"}]
    assert insp.fetch_all.call_count == 2


def test_fetch_snapshots_does_not_retry_timeout():
    from unittest.mock import MagicMock

    import pytest

    from core.exceptions import DataLoadError
    from snapshots.snapshot_inspector_sql import _fetch_snapshots

    insp = MagicMock()
    insp.fetch_all.side_effect = DataLoadError("statement timeout")
    with pytest.raises(DataLoadError, match="statement timeout"):
        _fetch_snapshots(insp, "guid")
    assert insp.fetch_all.call_count == 1

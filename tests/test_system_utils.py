"""Тесты системного раздела: вкладки и фенсинг."""

import pandas as pd

from core.data_loader import pick_engine_product_version
from system.system_utils import (
    SYSTEM_TAB_SQL,
    fence_agents_caption,
    fence_warning_needed,
    filter_system_rows,
    first_scalar_int,
    hosted_engine_caption,
)


def test_system_tabs_have_four_types_not_provider_option():
    assert set(SYSTEM_TAB_SQL) == {"sessions", "fence", "quota", "transfers"}
    blob = "\n".join(SYSTEM_TAB_SQL.values()).lower()
    assert "engine_sessions" in blob
    assert "fence_agents" in blob
    assert "from quota" in blob
    assert "image_transfers" in blob
    assert "from providers" not in blob
    assert "vdc_options" not in blob


def test_fence_warning_and_agents_caption():
    assert fence_warning_needed(3, 0) is True
    assert fence_warning_needed(3, 2) is False
    assert fence_warning_needed(0, 0) is False
    assert fence_agents_caption(4) == "агентов: 4"
    assert "активен" not in fence_agents_caption(4).lower()


def test_filter_system_rows():
    df = pd.DataFrame(
        {
            "name": ["admin", "host-a"],
            "status": ["Active", "ipmilan"],
            "details": ["10.0.0.1", "10.0.0.2"],
            "source": ["engine_sessions", "fence_agents"],
        }
    )
    assert len(filter_system_rows(df, "ipmilan")) == 1
    assert len(filter_system_rows(df, "")) == 2


def test_pick_engine_product_version_prefers_rpm():
    rows = [
        {"option_name": "VdcVersion", "option_value": "4.5", "version": "general"},
        {"option_name": "RPMVersion", "option_value": "4.5.6-1", "version": "4.5"},
        {"option_name": "RPMVersion", "option_value": "4.5.6-1.el8", "version": "general"},
    ]
    assert pick_engine_product_version(rows) == "4.5.6-1.el8"


def test_pick_engine_product_version_skips_empty():
    rows = [
        {"option_name": "RPMVersion", "option_value": "  ", "version": "general"},
        {"option_name": "EngineVersion", "option_value": "4.4", "version": "general"},
    ]
    assert pick_engine_product_version(rows) == "4.4"
    assert pick_engine_product_version([]) == "—"


def test_first_scalar_int_uses_position_not_column_name():
    df = pd.DataFrame({"count": [3]})
    assert first_scalar_int(df) == 3
    assert first_scalar_int(pd.DataFrame()) == 0


def test_hosted_engine_caption_none_and_counts():
    assert hosted_engine_caption(he_hosts=0, ha_active=0, he_disks=0) == "нет"
    assert (
        hosted_engine_caption(he_hosts=2, ha_active=1, he_disks=4)
        == "2 хостов, ha-agent 1, диски 4"
    )

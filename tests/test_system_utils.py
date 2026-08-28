"""Тесты системного раздела: вкладки и фенсинг."""

import pandas as pd

from system.system_utils import (
    SYSTEM_TAB_SQL,
    fence_agents_caption,
    fence_warning_needed,
    filter_system_rows,
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

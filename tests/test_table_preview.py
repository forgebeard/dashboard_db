"""Юнит-тесты для src/core/table_preview.py."""
import pytest

from core.table_preview import assert_safe_ident


@pytest.mark.parametrize("name", ["vds_static", "_tmp", "A1"])
def test_assert_safe_ident_ok(name):
    assert assert_safe_ident(name) == name


@pytest.mark.parametrize("name", ["vds;drop", "public.vds", "vds static", "1abc", ""])
def test_assert_safe_ident_rejects(name):
    with pytest.raises(ValueError):
        assert_safe_ident(name)

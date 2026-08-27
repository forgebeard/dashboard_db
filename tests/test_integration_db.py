"""
Интеграционные тесты для проверки подключения к реальной БД oVirt.
"""
import os

import pytest

pytestmark = pytest.mark.integration

_SYSTEM_DBS = {"postgres", "template0", "template1"}


@pytest.fixture(scope="module")
def check_env():
    if not os.getenv("DB_PASSWORD"):
        pytest.skip("DB_PASSWORD не задан в .env. Интеграционные тесты пропущены.")


def _pick_dump_db(dbs: list[str]) -> str:
    env_name = os.getenv("TEST_DB_NAME")
    if env_name:
        if env_name not in dbs:
            pytest.skip(f"TEST_DB_NAME={env_name!r} нет среди доступных БД: {dbs}")
        return env_name
    dumps = [name for name in dbs if name not in _SYSTEM_DBS]
    if not dumps:
        pytest.skip("Нет пользовательских БД для интеграционного теста.")
    return dumps[0]


def test_get_available_databases(check_env):
    from core.db_utils import get_available_databases

    dbs = get_available_databases()
    assert isinstance(dbs, list)
    if len(dbs) == 0:
        pytest.fail("Не удалось получить список БД.")
    print(f"Найдено БД: {dbs}")


def test_load_cluster_metadata_real_db(check_env):
    from core.db_utils import get_available_databases
    from core.data_loader import load_cluster_metadata

    dbs = get_available_databases()
    if not dbs:
        pytest.skip("Нет доступных БД.")

    target_db = _pick_dump_db(dbs)
    print(f"Тестирование БД: {target_db}")

    metadata = load_cluster_metadata(target_db)

    assert isinstance(metadata, dict)
    assert "clusters" in metadata
    assert "hosts" in metadata
    assert len(metadata["clusters"]) > 0
    assert len(metadata["hosts"]) > 0
    print(
        f"Успешно загружено: Кластеров={len(metadata['clusters'])}, "
        f"Хостов={len(metadata['hosts'])}"
    )

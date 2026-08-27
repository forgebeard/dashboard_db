"""
Интеграционные тесты для проверки подключения к реальной БД oVirt.
"""
import pytest
import os
# sys.path.append удален

pytestmark = pytest.mark.integration

@pytest.fixture(scope="module")
def check_env():
    if not os.getenv("DB_PASSWORD"):
        pytest.skip("DB_PASSWORD не задан в .env. Интеграционные тесты пропущены.")
    from dotenv import load_dotenv
    load_dotenv()

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
    
    target_db = "67785" if "67785" in dbs else dbs[0]
    print(f"Тестирование БД: {target_db}")
    
    metadata = load_cluster_metadata(target_db)
    
    assert isinstance(metadata, dict)
    assert 'clusters' in metadata
    assert 'hosts' in metadata
    assert len(metadata['clusters']) > 0
    assert len(metadata['hosts']) > 0
    print(f"Успешно загружено: Кластеров={len(metadata['clusters'])}, Хостов={len(metadata['hosts'])}")
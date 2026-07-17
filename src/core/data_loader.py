# src/core/data_loader.py
"""
Модуль бизнес-логики загрузки справочников (метаданных).

Отвечает за: преобразование сырых таблиц БД в удобные словари {ID: Имя} 
для фильтров UI, безопасной обработки ошибок и кэширования.
Использует единый движок подключения из core.db_utils.
Результаты кэшируются Streamlit для мгновенной работы интерфейса.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Доступ к переменным окружения (METADATA_CACHE_TTL)
import logging          # Логирование процесса загрузки метаданных и ошибок

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import pandas as pd          # Работа с табличными данными и SQL-запросами
from sqlalchemy import text  # Безопасное выполнение параметризованных SQL-выражений
from sqlalchemy.engine import Engine  # Типизация объекта движка SQLAlchemy
import streamlit as st       # Декоратор кэширования данных (@st.cache_data)

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import get_sqlalchemy_engine  # Утилита создания подключений к PostgreSQL

logger = logging.getLogger(__name__)

# TTL кэша метаданных (секунды). Можно переопределить через env-переменную
_CACHE_TTL = int(os.getenv("METADATA_CACHE_TTL", "300"))


def _safe_load_dict(engine: Engine, query: str, id_col: str, name_col: str) -> dict[str, str]:
    """
    Безопасно загружает словарь {ID: Name} из БД.
    
    Args:
        engine: Активный движок SQLAlchemy
        query: SQL-запрос для выборки данных
        id_col: Имя столбца с идентификатором (ключ словаря)
        name_col: Имя столбца с именем (значение словаря)
        
    Returns:
        Словарь {id: name} или пустой словарь при ошибке
    """
    try:
        df = pd.read_sql(text(query), engine)
        
        if df.empty:
            return {}
            
        # Фильтруем строки с NULL в ключе
        valid = df.dropna(subset=[id_col])
        
        if valid.empty:
            return {}
            
        result = dict(zip(valid[id_col], valid[name_col]))
        logger.debug(f"Загружено записей в '{name_col}': {len(result)}")
        return result
        
    except Exception as e:
        logger.warning(f"Ошибка загрузки '{name_col}' ({id_col}): {e}")
        return {}


@st.cache_data(ttl=_CACHE_TTL)
def load_cluster_metadata(db_name: str) -> dict[str, dict | list]:
    """
    Загружает основные справочники кластера и связи инфраструктуры.
    
    Результат используется в фильтрах модулей и инспекторах.
    ЗАКЭШИРОВАНО: повторные вызовы с тем же db_name возвращают результат мгновенно.
    
    Args:
        db_name: Имя базы данных (дампа) для загрузки метаданных
        
    Returns:
        Словарь со справочниками: clusters, storage_domains, hosts, datacenters,
                                  dc_to_clusters, cluster_to_hosts
    """
    if not db_name:
        logger.warning("Попытка загрузки метаданных с пустым db_name")
        return {}
        
    logger.info(f"Загрузка метаданных для БД: {db_name} (кэш промах)")
    
    engine: Engine = get_sqlalchemy_engine(db_name)
    metadata: dict[str, dict | list] = {}
    
    try:
        # 1. Кластеры
        metadata['clusters'] = _safe_load_dict(
            engine, 
            "SELECT cluster_id::text, COALESCE(name, 'Unknown') as name FROM cluster",
            'cluster_id', 'name'
        )

        # 2. Хранилища (Storage Domains)
        metadata['storage_domains'] = _safe_load_dict(
            engine, 
            "SELECT id::text, COALESCE(storage_name, 'Unknown') as storage_name FROM storage_domain_static",
            'id', 'storage_name'
        )

        # 3. Хосты (VDS)
        metadata['hosts'] = _safe_load_dict(
            engine, 
            "SELECT vds_id::text, COALESCE(vds_name, 'Unknown') as vds_name FROM vds_static",
            'vds_id', 'vds_name'
        )

        # 4. Дата-центры (Storage Pools)
        metadata['datacenters'] = _safe_load_dict(
            engine, 
            "SELECT id::text, COALESCE(name, 'Unknown') as name FROM storage_pool",
            'id', 'name'
        )

        # 5. Связи: ДЦ -> Кластеры
        try:
            df_dc_cl = pd.read_sql(
                text("SELECT storage_pool_id::text as spid, cluster_id::text as cid FROM cluster"),
                engine
            )
            dc_to_clusters: dict[str, list[str]] = {}
            if not df_dc_cl.empty:
                for _, row in df_dc_cl.iterrows():
                    dc_to_clusters.setdefault(row['spid'], []).append(row['cid'])
            metadata['dc_to_clusters'] = dc_to_clusters
        except Exception as e:
            logger.warning(f"Ошибка загрузки связей ДЦ->Кластеры: {e}")
            metadata['dc_to_clusters'] = {}

        # 6. Связи: Кластер -> Хосты
        try:
            df_cl_h = pd.read_sql(
                text("SELECT cluster_id::text as cid, vds_id::text as vid FROM vds_static"),
                engine
            )
            cluster_to_hosts: dict[str, list[str]] = {}
            if not df_cl_h.empty:
                for _, row in df_cl_h.iterrows():
                    cluster_to_hosts.setdefault(row['cid'], []).append(row['vid'])
            metadata['cluster_to_hosts'] = cluster_to_hosts
        except Exception as e:
            logger.warning(f"Ошибка загрузки связей Кластер->Хосты: {e}")
            metadata['cluster_to_hosts'] = {}
            
    finally:
        # Гарантированное освобождение ресурсов даже при ошибке
        engine.dispose()
        
    logger.info(f"Метаданные для '{db_name}' загружены: "
                f"DC={len(metadata.get('datacenters', {}))}, "
                f"Clusters={len(metadata.get('clusters', {}))}, "
                f"Hosts={len(metadata.get('hosts', {}))}, "
                f"SD={len(metadata.get('storage_domains', {}))}")
                
    return metadata
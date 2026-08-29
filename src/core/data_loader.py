# src/core/data_loader.py
"""
Модуль бизнес-логики загрузки справочников (метаданных).

Отвечает за: преобразование сырых таблиц БД в удобные словари {ID: Имя} 
для фильтров UI, безопасной обработки ошибок и кэширования.
Использует единый движок подключения из core.db_utils.
Результаты кэшируются Streamlit для мгновенной работы интерфейса.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import logging  # Логирование процесса загрузки метаданных и ошибок
import os  # Доступ к переменным окружения (METADATA_CACHE_TTL)

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
import streamlit as st  # Декоратор кэширования данных (@st.cache_data)
from sqlalchemy import text  # Безопасное выполнение параметризованных SQL-выражений
from sqlalchemy.engine import Engine  # Типизация объекта движка SQLAlchemy

# --- ВНУТРЕННИЕ МОДУЛИ ПРОЕКТА (CORE) ---
from core.db_utils import (
    get_sqlalchemy_engine,
    read_sql_df,
)
from core.exceptions import DataLoadError

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
        df = read_sql_df(engine, text(query))
        
        if df.empty:
            return {}
            
        # Фильтруем строки с NULL в ключе
        valid = df.dropna(subset=[id_col])
        
        if valid.empty:
            return {}
            
        result = dict(zip(valid[id_col], valid[name_col]))
        logger.debug(f"Загружено записей в '{name_col}': {len(result)}")
        return result
        
    except DataLoadError as e:
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
        df_dc_cl = read_sql_df(
            engine,
            text("SELECT storage_pool_id::text as spid, cluster_id::text as cid FROM cluster"),
        )
        dc_to_clusters: dict[str, list[str]] = {}
        if not df_dc_cl.empty:
            for _, row in df_dc_cl.iterrows():
                dc_to_clusters.setdefault(row['spid'], []).append(row['cid'])
        metadata['dc_to_clusters'] = dc_to_clusters
    except DataLoadError as e:
        logger.warning(f"Ошибка загрузки связей ДЦ->Кластеры: {e}")
        metadata['dc_to_clusters'] = {}

    # 6. Связи: Кластер -> Хосты
    try:
        df_cl_h = read_sql_df(
            engine,
            text("SELECT cluster_id::text as cid, vds_id::text as vid FROM vds_static"),
        )
        cluster_to_hosts: dict[str, list[str]] = {}
        if not df_cl_h.empty:
            for _, row in df_cl_h.iterrows():
                cluster_to_hosts.setdefault(row['cid'], []).append(row['vid'])
        metadata['cluster_to_hosts'] = cluster_to_hosts
    except DataLoadError as e:
        logger.warning(f"Ошибка загрузки связей Кластер->Хосты: {e}")
        metadata['cluster_to_hosts'] = {}

    logger.info(f"Метаданные для '{db_name}' загружены: "
                f"DC={len(metadata.get('datacenters', {}))}, "
                f"Clusters={len(metadata.get('clusters', {}))}, "
                f"Hosts={len(metadata.get('hosts', {}))}, "
                f"SD={len(metadata.get('storage_domains', {}))}")
                
    return metadata


def build_infra_filter_maps(cluster_meta: dict) -> dict[str, dict | list]:
    """
    Справочники фильтров UI из уже загруженного cluster_meta.
    Не ходит в БД (в отличие от load_audit_infrastructure_maps / load_host_infrastructure_maps).
    """
    meta = cluster_meta or {}

    def _str_map(raw: dict) -> dict[str, str]:
        return {str(k): v for k, v in (raw or {}).items() if k is not None}

    def _str_list_map(raw: dict) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for key, values in (raw or {}).items():
            if key is None:
                continue
            result[str(key)] = [str(v) for v in (values or []) if v is not None]
        return result

    return {
        "dc_id_to_name": _str_map(meta.get("datacenters", {})),
        "cluster_id_to_name": _str_map(meta.get("clusters", {})),
        "host_id_to_name": _str_map(meta.get("hosts", {})),
        "dc_to_clusters": _str_list_map(meta.get("dc_to_clusters", {})),
        "cluster_to_hosts": _str_list_map(meta.get("cluster_to_hosts", {})),
        "host_to_vms": {},
        "vm_id_to_name": {},
    }


def _id_by_name(name_map: dict, selected: str) -> str | None:
    return next((key for key, value in (name_map or {}).items() if value == selected), None)


def host_ids_for_infra_filters(
    maps: dict,
    selected_dc: str,
    selected_cluster: str,
    selected_host: str,
    *,
    all_dc: str = "Все ДЦ",
    all_cluster: str = "Все кластеры",
    all_host: str = "Все хосты",
) -> list[str] | None:
    """
    Срез vds_id по каскаду ДЦ / кластер / хост.

    None — ограничение по хостам не нужно (все «Все»).
    [] — выбран ДЦ или кластер без хостов (пустой результат, не весь лог).
    """
    maps = maps or {}
    host_names = maps.get("host_id_to_name") or {}
    cluster_names = maps.get("cluster_id_to_name") or {}
    dc_names = maps.get("dc_id_to_name") or {}
    dc_to_clusters = maps.get("dc_to_clusters") or {}
    cluster_to_hosts = maps.get("cluster_to_hosts") or {}

    if selected_host != all_host:
        host_id = _id_by_name(host_names, selected_host)
        return [host_id] if host_id else []

    if selected_cluster != all_cluster:
        cluster_id = _id_by_name(cluster_names, selected_cluster)
        if not cluster_id:
            return []
        return list(cluster_to_hosts.get(cluster_id) or [])

    if selected_dc != all_dc:
        dc_id = _id_by_name(dc_names, selected_dc)
        if not dc_id:
            return []
        host_ids: list[str] = []
        seen: set[str] = set()
        for cluster_id in dc_to_clusters.get(dc_id) or []:
            for host_id in cluster_to_hosts.get(cluster_id) or []:
                if host_id and host_id not in seen:
                    seen.add(host_id)
                    host_ids.append(host_id)
        return host_ids

    return None
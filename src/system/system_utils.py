# src/system/system_utils.py
"""Данные раздела «Системные»: сессии, фенсинг, квоты, трансферы."""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.constants import DISK_CONTENT_TYPE_MAP
from core.db_utils import get_sqlalchemy_engine, load_sql_df, read_sql_df
from core.exceptions import DataLoadError, should_retry_narrow_sql
from core.ui_utils import fix_uuid_columns

_HE_DISK_CONTENT_TYPES = tuple(
    code
    for code, label in DISK_CONTENT_TYPE_MAP.items()
    if str(label).startswith("HOSTED_ENGINE")
)

logger = logging.getLogger(__name__)

SYSTEM_TAB_SQL = {
    "sessions": """
        SELECT
            user_name AS name,
            'Active' AS status,
            source_ip AS details,
            'engine_sessions' AS source
        FROM engine_sessions
    """,
    "fence": """
        SELECT
            v.vds_name AS name,
            fa.type AS status,
            CONCAT(fa.ip, ':', COALESCE(fa.port::text, '')) AS details,
            'fence_agents' AS source
        FROM fence_agents fa
        JOIN vds_static v ON fa.vds_id = v.vds_id
    """,
    "quota": """
        SELECT
            q.quota_name AS name,
            CONCAT(
                'Cluster:', q.threshold_cluster_percentage, '% | Storage:',
                q.threshold_storage_percentage, '%'
            ) AS status,
            CONCAT('Grace: ', q.grace_cluster_percentage, '%') AS details,
            'quota' AS source
        FROM quota q
    """,
    "transfers": """
        SELECT
            disk_id::text AS name,
            CASE phase
                WHEN 0 THEN 'Initializing'
                WHEN 1 THEN 'Transferring'
                WHEN 2 THEN 'Finished'
                ELSE 'Unknown'
            END AS status,
            CONCAT(bytes_sent::text, ' / ', bytes_total::text, ' bytes') AS details,
            'image_transfers' AS source
        FROM image_transfers
        WHERE active = true
    """,
}

SYSTEM_TAB_LABELS = {
    "sessions": "Сессии",
    "fence": "Фенсинг",
    "quota": "Квоты",
    "transfers": "Трансферы",
}


def filter_system_rows(df: pd.DataFrame, search_term: str) -> pd.DataFrame:
    if df.empty or not search_term:
        return df
    mask = df.apply(
        lambda row: row.astype(str).str.contains(search_term, case=False, na=False).any(),
        axis=1,
    )
    return df[mask]


def fence_warning_needed(host_count: int, fence_configured: int) -> bool:
    return host_count > 0 and fence_configured == 0


def fence_agents_caption(fence_configured: int) -> str:
    return f"агентов: {fence_configured}"


def hosted_engine_caption(*, he_hosts: int, ha_active: int, he_disks: int) -> str:
    if he_hosts <= 0 and he_disks <= 0:
        return "нет"
    return f"{he_hosts} хостов, ha-agent {ha_active}, диски {he_disks}"


def first_scalar_int(df: pd.DataFrame) -> int:
    """Первая ячейка по позиции (COUNT(*) приходит как колонка count, не 0)."""
    if df.empty:
        return 0
    val = df.iloc[0, 0]
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0
    return int(val)


def _count_sql(engine: Engine, sql: str) -> int:
    return first_scalar_int(read_sql_df(engine, text(sql)))


def _count_he_hosts(engine: Engine) -> int:
    try:
        return _count_sql(
            engine,
            """
            SELECT COUNT(*) FROM vds_static s
            LEFT JOIN vds_dynamic d ON d.vds_id = s.vds_id
            WHERE s.vds_type = 1 OR d.hosted_engine_configured IS TRUE
            """,
        )
    except DataLoadError as exc:
        if not should_retry_narrow_sql(exc):
            logger.warning("HE-хосты: %s", exc)
            return 0
    try:
        return _count_sql(
            engine, "SELECT COUNT(*) FROM vds_static WHERE vds_type = 1"
        )
    except DataLoadError as exc:
        logger.warning("HE-хосты (vds_type): %s", exc)
        return 0


def _count_ha_active(engine: Engine) -> int:
    queries = (
        """
        SELECT COUNT(*) FROM vds_statistics
        WHERE ha_configured IS TRUE OR ha_active IS TRUE
        """,
        "SELECT COUNT(*) FROM vds_statistics WHERE ha_active IS TRUE",
        "SELECT COUNT(*) FROM vds_statistics WHERE ha_configured IS TRUE",
    )
    last_exc: DataLoadError | None = None
    for sql in queries:
        try:
            return _count_sql(engine, sql)
        except DataLoadError as exc:
            last_exc = exc
            if not should_retry_narrow_sql(exc):
                logger.warning("ha-agent: %s", exc)
                return 0
    if last_exc is not None:
        logger.warning("ha-agent: %s", last_exc)
    return 0


def _count_he_disks(engine: Engine) -> int:
    if not _HE_DISK_CONTENT_TYPES:
        return 0
    types_sql = ", ".join(str(code) for code in _HE_DISK_CONTENT_TYPES)
    try:
        return _count_sql(
            engine,
            f"SELECT COUNT(*) FROM base_disks WHERE disk_content_type IN ({types_sql})",
        )
    except DataLoadError as exc:
        logger.warning("HE-диски: %s", exc)
        return 0


def fetch_system_tab(active_db: str, tab_id: str) -> pd.DataFrame:
    sql = SYSTEM_TAB_SQL[tab_id]
    df = load_sql_df(active_db, text(sql))
    return fix_uuid_columns(df)


def get_system_summary(active_db: str) -> dict:
    summary = {
        "hosted_engine": "нет",
        "sessions_count": 0,
        "fence_configured": 0,
        "active_transfers": 0,
        "custom_options": 0,
        "quota_count": 0,
    }
    try:
        engine = get_sqlalchemy_engine(active_db)
        he_hosts = _count_he_hosts(engine)
        ha_active = _count_ha_active(engine)
        he_disks = _count_he_disks(engine)
        summary["hosted_engine"] = hosted_engine_caption(
            he_hosts=he_hosts, ha_active=ha_active, he_disks=he_disks
        )

        counts = read_sql_df(
            engine,
            text(
                """
            SELECT
                (SELECT COUNT(*) FROM engine_sessions) as sess,
                (SELECT COUNT(*) FROM fence_agents) as fence,
                (SELECT COUNT(*) FROM image_transfers WHERE active = true) as trans,
                (SELECT COUNT(*) FROM vdc_options
                 WHERE option_value != default_value AND default_value IS NOT NULL) as opts,
                (SELECT COUNT(*) FROM quota) as quota
            """
            ),
        )
        if not counts.empty:
            row = counts.iloc[0]
            summary["sessions_count"] = int(row["sess"])
            summary["fence_configured"] = int(row["fence"])
            summary["active_transfers"] = int(row["trans"])
            summary["custom_options"] = int(row["opts"])
            summary["quota_count"] = int(row["quota"])
    except DataLoadError as e:
        logger.warning("Не удалось загрузить сводку: %s", e)
    return summary

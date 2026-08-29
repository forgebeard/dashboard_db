# src/system/system_utils.py
"""Данные раздела «Системные»: сессии, фенсинг, квоты, трансферы."""

import logging

import pandas as pd
from sqlalchemy import text

from core.db_utils import get_sqlalchemy_engine, read_sql_df
from core.exceptions import DataLoadError
from core.ui_utils import fix_uuid_columns

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


def fetch_system_tab(active_db: str, tab_id: str) -> pd.DataFrame:
    sql = SYSTEM_TAB_SQL[tab_id]
    engine = get_sqlalchemy_engine(active_db)
    df = read_sql_df(engine, text(sql))
    return fix_uuid_columns(df)


def get_system_summary(active_db: str) -> dict:
    summary = {
        "schema_version": "—",
        "sessions_count": 0,
        "fence_configured": 0,
        "active_transfers": 0,
        "custom_options": 0,
        "quota_count": 0,
    }
    try:
        engine = get_sqlalchemy_engine(active_db)
        df_ver = read_sql_df(
            engine,
            text("SELECT version FROM schema_version WHERE current = true LIMIT 1"),
        )
        if not df_ver.empty:
            summary["schema_version"] = df_ver.iloc[0]["version"]

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
    except (DataLoadError, Exception) as e:
        logger.warning("Не удалось загрузить сводку: %s", e)
    return summary

# src/users/users_utils.py
"""SQL и подготовка списка пользователей."""

import pandas as pd
from sqlalchemy import text
import streamlit as st

from core.constants import vdc_object_type_label
from core.db_utils import get_sqlalchemy_engine


def build_users_list_sql(selected_domain: str, search_term: str) -> tuple[str, dict]:
    sql = """
        SELECT
            u.user_id::text AS _user_id,
            u.name,
            u.domain,
            COUNT(p.id) AS permission_count,
            COUNT(DISTINCT p.role_id) AS role_count
        FROM users u
        LEFT JOIN permissions p ON p.ad_element_id = u.user_id
        WHERE TRUE
    """
    params: dict = {}
    if selected_domain and selected_domain != "Все домены":
        sql += " AND u.domain = :domain"
        params["domain"] = selected_domain
    if search_term:
        sql += " AND (LOWER(u.name) LIKE LOWER(:search) OR u.user_id::text LIKE LOWER(:search))"
        params["search"] = f"%{search_term}%"
    sql += " GROUP BY u.user_id, u.name, u.domain ORDER BY u.name"
    return sql, params


def build_user_domains_sql() -> str:
    return """
        SELECT DISTINCT domain
        FROM users
        WHERE domain IS NOT NULL AND BTRIM(domain) <> ''
        ORDER BY 1
    """


def build_user_permissions_sql() -> str:
    return """
        SELECT
            r.name AS role_name,
            p.object_type_id,
            p.object_id::text AS object_id,
            COALESCE(
                bd.disk_alias,
                vm.vm_name,
                vds.vds_name,
                sd.storage_name,
                cl.name,
                sp.name
            ) AS object_name
        FROM permissions p
        JOIN roles r ON r.id = p.role_id
        LEFT JOIN base_disks bd
            ON p.object_type_id = 19 AND bd.disk_id = p.object_id
        LEFT JOIN vm_static vm
            ON p.object_type_id = 5 AND vm.vm_guid = p.object_id
        LEFT JOIN vds_static vds
            ON p.object_type_id = 8 AND vds.vds_id = p.object_id
        LEFT JOIN storage_domain_static sd
            ON p.object_type_id = 3 AND sd.id = p.object_id
        LEFT JOIN cluster cl
            ON p.object_type_id = 9 AND cl.cluster_id = p.object_id
        LEFT JOIN storage_pool sp
            ON p.object_type_id = 4 AND sp.id = p.object_id
        WHERE p.ad_element_id::text = :uid
        ORDER BY r.name, p.object_type_id, object_name
    """


def fetch_user_domains(active_db: str) -> list[str]:
    try:
        engine = get_sqlalchemy_engine(active_db)
        df = pd.read_sql(text(build_user_domains_sql()), engine)
        return [str(v) for v in df["domain"].tolist() if v]
    except Exception as e:
        st.error(f"Ошибка загрузки доменов: {e}")
        return []


def fetch_users_data(active_db: str, filters: tuple[str, str]) -> pd.DataFrame:
    selected_domain, search_term = filters
    sql, sql_params = build_users_list_sql(selected_domain, search_term.strip() if search_term else "")
    try:
        engine = get_sqlalchemy_engine(active_db)
        return pd.read_sql(text(sql), engine, params=sql_params if sql_params else None)
    except Exception as e:
        st.error(f"Ошибка загрузки пользователей: {e}")
        return pd.DataFrame()


def fetch_user_permissions(active_db: str, user_id: str) -> pd.DataFrame:
    try:
        engine = get_sqlalchemy_engine(active_db)
        return pd.read_sql(
            text(build_user_permissions_sql()),
            engine,
            params={"uid": str(user_id)},
        )
    except Exception as e:
        st.error(f"Ошибка загрузки прав: {e}")
        return pd.DataFrame()


def process_user_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    display_df = df[
        ["name", "_user_id", "domain", "role_count", "permission_count"]
    ].copy()
    display_df.columns = ["Имя", "UUID", "Домен", "Ролей", "Прав"]
    return display_df


def _short_uuid(value: object) -> str:
    text_id = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    if not text_id or text_id.lower() in ("none", "nan"):
        return "—"
    return text_id[:8]


def _object_display(row: pd.Series) -> str:
    name = row.get("object_name")
    if name is not None and not (isinstance(name, float) and pd.isna(name)):
        text_name = str(name).strip()
        if text_name and text_name.lower() not in ("none", "nan"):
            return text_name
    return _short_uuid(row.get("object_id"))


def format_user_role_summary(permissions: pd.DataFrame) -> str:
    if permissions is None or permissions.empty:
        return "Назначений ролей нет."
    work = permissions.copy()
    work["Тип"] = work["object_type_id"].map(vdc_object_type_label)
    work["Роль"] = work["role_name"].fillna("—")
    counts = (
        work.groupby(["Роль", "Тип"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["Роль", "Тип"])
    )
    return "\n".join(
        f"{row['Роль']} — {int(row['n'])}× {row['Тип']}" for _, row in counts.iterrows()
    )


def process_user_permissions_table(permissions: pd.DataFrame) -> pd.DataFrame:
    if permissions is None or permissions.empty:
        return pd.DataFrame(columns=["Роль", "Тип", "Объект"])
    work = permissions.copy()
    work["Роль"] = work["role_name"].fillna("—")
    work["Тип"] = work["object_type_id"].map(vdc_object_type_label)
    work["Объект"] = work.apply(_object_display, axis=1)
    return work[["Роль", "Тип", "Объект"]].reset_index(drop=True)

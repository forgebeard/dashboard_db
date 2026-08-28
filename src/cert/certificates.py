# src/cert/certificates.py
from pathlib import Path

import pandas as pd
import streamlit as st

from core.db_utils import get_sqlalchemy_engine
from core.ui_utils import dataframe_height

COLUMN_CONFIG = {
    "Файл": st.column_config.TextColumn(width=220),
    "Каталог": st.column_config.TextColumn(),
    "Окончание": st.column_config.DateColumn(width=110, format="DD.MM.YYYY"),
    "_expired": None,
}


def _is_expired(value) -> bool:
    if value in (True, 1, "1", "t", "true", "True"):
        return True
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return False


def _highlight_expired(row):
    color = "background-color: #ffcccc" if _is_expired(row.get("_expired")) else ""
    return [color] * len(row)


def _split_path(raw) -> tuple[str, str]:
    if raw is None:
        return "—", "—"
    try:
        if pd.isna(raw):
            return "—", "—"
    except (TypeError, ValueError):
        pass
    text = str(raw).strip()
    if not text:
        return "—", "—"
    path = Path(text)
    name = path.name or "—"
    folder = path.parent.as_posix()
    if folder in (".", ""):
        folder = "—"
    return name, folder


def _display_certs(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        name, folder = _split_path(row.get("file_path"))
        rows.append(
            {
                "Файл": name,
                "Каталог": folder,
                "Окончание": row.get("expires_at"),
                "_expired": row.get("expired"),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(by=["Каталог", "Файл"], kind="mergesort").reset_index(
        drop=True
    )


def _show_table(display_df: pd.DataFrame) -> None:
    st.dataframe(
        display_df.style.apply(_highlight_expired, axis=1),
        width="stretch",
        hide_index=True,
        column_config=COLUMN_CONFIG,
        height=dataframe_height(len(display_df)),
    )


def render_certificates(db_name):
    query = """
    SELECT
        cd.object_type_id,
        vs.vds_name,
        cd.file_path,
        cd.valid_not_after AS expires_at,
        cd.expired
    FROM certificates_data cd
    LEFT JOIN vds_static vs ON cd.object_id = vs.vds_id
    WHERE cd.object_type_id IN (2, 3)
    ORDER BY vs.vds_name, cd.file_path
    """

    try:
        engine = get_sqlalchemy_engine(db_name)
        df = pd.read_sql_query(query, engine)

        if df.empty:
            st.info("Сертификаты не найдены.")
            return

        st.subheader("Engine")
        engine_src = df[df["object_type_id"] == 2]
        engine_df = _display_certs(engine_src)
        if not engine_df.empty:
            _show_table(engine_df)
        else:
            st.warning("Нет данных по сертификатам Engine.")

        hosts_src = df[df["object_type_id"] == 3].copy()
        if hosts_src.empty:
            st.warning("Нет данных по сертификатам хостов.")
            return

        st.subheader("Хосты")
        hosts_src["vds_name"] = hosts_src["vds_name"].fillna("—")
        for host in sorted(hosts_src["vds_name"].unique(), key=str):
            host_df = _display_certs(hosts_src[hosts_src["vds_name"] == host])
            st.markdown(f"### {host}")
            if host_df.empty:
                st.info("Нет сертификатов.")
            else:
                _show_table(host_df)

    except Exception as e:
        st.error(f"Ошибка при загрузке сертификатов: {e}")

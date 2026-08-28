# src/cert/certificates.py
import streamlit as st
import pandas as pd

from core.db_utils import get_sqlalchemy_engine


def _highlight_expiry(row):
    days = row.get("days_left")
    try:
        if pd.isna(days):
            return [""] * len(row)
        days = int(days)
    except (TypeError, ValueError):
        return [""] * len(row)
    if days < 0:
        color = "background-color: #ffcccc"
    elif days <= 30:
        color = "background-color: #ffffcc"
    else:
        color = ""
    return [color] * len(row)


def render_certificates(db_name):
    query = """
    SELECT
        cd.object_type_id,
        vs.vds_name,
        cd.subject_comname AS cert_name,
        cd.file_path,
        cd.valid_not_after AS expires_at,
        cd.expired,
        EXTRACT(DAY FROM (cd.valid_not_after - NOW()))::INTEGER AS days_left
    FROM certificates_data cd
    LEFT JOIN vds_static vs ON cd.object_id = vs.vds_id
    WHERE cd.object_type_id IN (2, 3)
    GROUP BY cd.object_type_id, vs.vds_name, cd.subject_comname, cd.file_path, cd.valid_not_after, cd.expired
    ORDER BY cd.object_type_id ASC, days_left ASC;
    """

    try:
        engine = get_sqlalchemy_engine(db_name)
        df = pd.read_sql_query(query, engine)

        if df.empty:
            st.info("Сертификаты не найдены.")
            return

        st.caption(
            "Остаток дней считается относительно текущего времени сервера БД, "
            "не момента снятия дампа. Ориентир — дата окончания."
        )

        column_config = {
            "cert_name": st.column_config.TextColumn("Имя сертификата", width="auto"),
            "file_path": st.column_config.TextColumn("Путь к файлу", width="auto"),
            "expires_at": st.column_config.DateColumn(
                "Дата окончания", format="DD.MM.YYYY", width="auto"
            ),
            "days_left": st.column_config.NumberColumn(
                "Осталось дней", format="%d дн.", width="auto"
            ),
        }

        st.subheader("Engine Certificates")
        engine_df = df[df["object_type_id"] == 2][
            ["cert_name", "file_path", "expires_at", "days_left"]
        ]

        if not engine_df.empty:
            st.dataframe(
                engine_df.style.apply(_highlight_expiry, axis=1),
                width="stretch",
                hide_index=True,
                column_config=column_config,
            )
        else:
            st.warning("Нет данных по сертификатам Engine.")

        st.subheader("Host Certificates")
        hosts_df = df[df["object_type_id"] == 3][
            ["vds_name", "cert_name", "file_path", "expires_at", "days_left"]
        ]

        if not hosts_df.empty:
            hosts_df = hosts_df.sort_values(by=["vds_name", "days_left"])
            for host in hosts_df["vds_name"].unique():
                host_certs = hosts_df[hosts_df["vds_name"] == host].drop(
                    columns=["vds_name"]
                )
                st.markdown(f"### {host}")
                st.dataframe(
                    host_certs.style.apply(_highlight_expiry, axis=1),
                    width="stretch",
                    hide_index=True,
                    column_config=column_config,
                )
        else:
            st.warning("Нет данных по сертификатам хостов.")

    except Exception as e:
        st.error(f"Ошибка при загрузке сертификатов: {e}")

# src/cert/certificates.py
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os

def get_engine(db_name):
    user = os.getenv('DB_USER', 'postgres')
    password = os.getenv('DB_PASSWORD')
    host = os.getenv('DB_HOST', 'localhost')
    port = os.getenv('DB_PORT', '5432')
    return create_engine(f"postgresql://{user}:{password}@{host}:{port}/{db_name}")

def render_certificates(db_name):
    st.header("Мониторинг сертификатов")
    
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
        engine = get_engine(db_name)
        df = pd.read_sql_query(query, engine)
        engine.dispose()

        if df.empty:
            st.info("Сертификаты не найдены.")
            return

        # Конфигурация колонок
        column_config = {
            "cert_name": st.column_config.TextColumn("Имя сертификата", width="auto"),
            "file_path": st.column_config.TextColumn("Путь к файлу", width="auto"),
            "expires_at": st.column_config.DateColumn("Дата окончания", format="DD.MM.YYYY", width="auto"),
            "days_left": st.column_config.NumberColumn("Осталось дней", format="%d дн.", width="auto"),
        }

        # --- Блок 1: Сертификаты Engine ---
        st.subheader("Engine Certificates")
        engine_df = df[df['object_type_id'] == 2][['cert_name', 'file_path', 'expires_at', 'days_left']]
        
        if not engine_df.empty:
            def highlight_expiry(s):
                color = ''
                if s['days_left'] <= 30:
                    color = 'background-color: #ffffcc'
                elif s['days_left'] < 0:
                    color = 'background-color: #ffcccc'
                return [color] * len(s)

            st.dataframe(
                engine_df.style.apply(highlight_expiry, axis=1),
                width='stretch',  # Заменяет use_container_width=True
                hide_index=True,
                column_config=column_config
            )
            
            csv_engine = engine_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="Скачать CSV (Engine)", data=csv_engine, file_name=f"certs_engine_{db_name}.csv", mime="text/csv")
        else:
            st.warning("Нет данных по сертификатам Engine.")


        # --- Блок 2: Сертификаты Хостов ---
        st.subheader("Host Certificates")
        hosts_df = df[df['object_type_id'] == 3][['vds_name', 'cert_name', 'file_path', 'expires_at', 'days_left']]

        if not hosts_df.empty:
            hosts_df = hosts_df.sort_values(by=['vds_name', 'days_left'])
            unique_hosts = hosts_df['vds_name'].unique()
            
            for host in unique_hosts:
                host_certs = hosts_df[hosts_df['vds_name'] == host].drop(columns=['vds_name'])
                
                st.markdown(f"### {host}")
                
                def highlight_host_expiry(s):
                    color = ''
                    if s['days_left'] <= 30:
                        color = 'background-color: #ffffcc'
                    elif s['days_left'] < 0:
                        color = 'background-color: #ffcccc'
                    return [color] * len(s)

                st.dataframe(
                    host_certs.style.apply(highlight_host_expiry, axis=1),
                    width='stretch',  # Заменяет use_container_width=True
                    hide_index=True,
                    column_config=column_config
                )

            csv_all_hosts = hosts_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="Скачать CSV (All Hosts)", data=csv_all_hosts, file_name=f"certs_all_hosts_{db_name}.csv", mime="text/csv")

        else:
            st.warning("Нет данных по сертификатам хостов.")

    except Exception as e:
        st.error(f"Ошибка при загрузке сертификатов: {e}")
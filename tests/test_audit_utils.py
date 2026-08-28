"""Тесты SQL журнала: срез по хостам ДЦ и точный код severity."""

import pandas as pd

from audit.audit_utils import (
    build_audit_logs_sql,
    format_audit_event_detail,
    process_audit_dataframe,
)
from core.constants import audit_health_counts


def test_audit_sql_no_host_constraint():
    sql, params = build_audit_logs_sql({"host_ids": None, "severity_code": None}, 100)
    assert "IN :host_ids" not in sql
    assert "AND 1=0" not in sql
    assert "severity =" not in sql
    assert params["lim"] == 100


def test_audit_sql_host_ids_in():
    sql, params = build_audit_logs_sql({"host_ids": ["h-1", "h-2"]}, 50)
    assert "vds_id::text IN :host_ids" in sql
    assert params["host_ids"] == ("h-1", "h-2")


def test_audit_sql_empty_host_ids():
    sql, params = build_audit_logs_sql({"host_ids": []}, 50)
    assert "AND 1=0" in sql
    assert "host_ids" not in params


def test_audit_sql_severity_exact_code():
    sql, params = build_audit_logs_sql({"severity_code": 2}, 50)
    assert "severity = :sev_code" in sql
    assert "severity >=" not in sql
    assert params["sev_code"] == 2


def test_audit_sql_search_event_and_message():
    sql, params = build_audit_logs_sql({"search": "USER_ADD"}, 50)
    assert "log_type_name" in sql
    assert "message" in sql
    assert params["q"] == "%USER_ADD%"


def test_audit_health_counts_and_pills():
    df = pd.DataFrame(
        {
            "log_time": ["t", "t", "t", "t"],
            "log_type_name": ["A", "B", "C", "D"],
            "severity": [0, 1, 2, 3],
            "message": ["ok", "warn", "err", "alert"],
            "vds_name": ["h"] * 4,
            "vm_name": ["vm"] * 4,
            "user_name": ["u"] * 4,
        }
    )
    counts = audit_health_counts(df["severity"])
    assert counts == {"total": 4, "warning": 1, "errors": 2}
    warning = process_audit_dataframe(df, health_filter="warning")
    assert len(warning) == 1
    assert warning.iloc[0]["Ур."] == "Warning"
    errors = process_audit_dataframe(df, health_filter="errors")
    assert len(errors) == 2
    assert set(errors["Ур."]) == {"Error", "Alert"}
    all_rows = process_audit_dataframe(df, health_filter="all")
    assert len(all_rows) == 4
    assert "Normal" in set(all_rows["Ур."])


def test_audit_event_detail_lists_ids():
    row = pd.Series(
        {
            "message": "full text here",
            "log_type_name": "VM_DOWN",
            "user_id": "u-1",
            "user_name": "admin",
            "vm_id": "vm-1",
            "vm_name": "web",
            "vds_id": "h-1",
            "vds_name": "host",
            "cluster_id": "c-1",
            "cluster_name": "cl",
            "storage_domain_id": None,
            "storage_domain_name": None,
            "job_id": "j-1",
            "correlation_id": "corr-1",
            "audit_log_id": 9,
        }
    )
    text = format_audit_event_detail(row)
    assert "full text here" in text
    assert "vm_id: vm-1" in text
    assert "correlation_id: corr-1" in text
    assert "storage_domain_id: —" in text

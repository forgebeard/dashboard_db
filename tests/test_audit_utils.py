"""Тесты SQL журнала: срез по хостам ДЦ и точный код severity."""

from audit.audit_utils import build_audit_logs_sql


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

"""Тесты списка пользователей: домены, counts, деталь ролей."""

import pandas as pd

from users.users_utils import (
    build_user_domains_sql,
    build_user_permissions_sql,
    build_users_list_sql,
    format_user_role_summary,
    process_user_dataframe,
    process_user_permissions_table,
)


def test_users_sql_counts_and_domain_filter():
    sql, params = build_users_list_sql("internal", "admin")
    assert "COUNT(p.id) AS permission_count" in sql
    assert "COUNT(DISTINCT p.role_id) AS role_count" in sql
    assert "LEFT JOIN permissions p ON p.ad_element_id = u.user_id" in sql
    assert "u.domain = :domain" in sql
    assert params["domain"] == "internal"
    assert params["search"] == "%admin%"


def test_users_sql_all_domains():
    sql, params = build_users_list_sql("Все домены", "")
    assert "u.domain =" not in sql
    assert params == {}


def test_user_domains_sql_distinct():
    sql = build_user_domains_sql()
    assert "SELECT DISTINCT domain" in sql
    assert "FROM users" in sql


def test_user_permissions_sql():
    sql = build_user_permissions_sql()
    assert "JOIN roles r ON r.id = p.role_id" in sql
    assert "p.ad_element_id::text = :uid" in sql
    assert "base_disks" in sql
    assert "object_type_id" in sql
    assert "object_id" in sql


def test_process_user_dataframe_columns():
    df = pd.DataFrame(
        {
            "_user_id": ["u1"],
            "name": ["admin"],
            "domain": ["internal"],
            "role_count": [2],
            "permission_count": [5],
        }
    )
    show = process_user_dataframe(df)
    assert list(show.columns) == ["Имя", "UUID", "Домен", "Ролей", "Прав"]
    assert show.iloc[0]["Ролей"] == 2
    assert show.iloc[0]["Прав"] == 5


def test_user_role_summary_groups_disk_operator():
    empty = format_user_role_summary(pd.DataFrame())
    assert "нет" in empty.lower()
    rows = [
        {
            "role_name": "DiskOperator",
            "object_type_id": 19,
            "object_id": f"disk-{i:02d}-aaaa-bbbb-cccc-dddddddddddd",
            "object_name": f"disk-{i}",
        }
        for i in range(17)
    ]
    rows.append(
        {
            "role_name": "UserRole",
            "object_type_id": 5,
            "object_id": "vm-1",
            "object_name": "web",
        }
    )
    perms = pd.DataFrame(rows)
    summary = format_user_role_summary(perms)
    assert "DiskOperator — 17× диск" in summary
    assert "UserRole — 1× ВМ" in summary
    assert "object_type_id=19" not in summary
    table = process_user_permissions_table(perms)
    assert list(table.columns) == ["Роль", "Тип", "Объект"]
    assert len(table) == 18
    disk_rows = table[table["Роль"] == "DiskOperator"]
    assert (disk_rows["Тип"] == "диск").all()
    assert "disk-0" in set(disk_rows["Объект"])

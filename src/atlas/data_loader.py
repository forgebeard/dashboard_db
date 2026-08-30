"""
Загрузчик данных атласа схемы БД.
Автоматически сканирует директорию data/ и объединяет все JSON-файлы справочника.
Overlay совместимости 7.3/8 живёт рядом, не в data/.
"""

import json
from pathlib import Path
from typing import Any

import streamlit as st

ATLAS_DIR = Path(__file__).resolve().parent / "data"
COMPAT_PATH = Path(__file__).resolve().parent / "compat.json"
CHANGELOG_PATH = Path(__file__).resolve().parent / "changelog.json"

RELEASE_LABELS = {
    "7.3": "РЕД ВИРТ 7.3",
    "8": "РЕД ВИРТ 8",
}


def release_key_from_label(label: str | None) -> str | None:
    """Подпись шапки → короткий ключ overlay."""
    if label == RELEASE_LABELS["8"]:
        return "8"
    if label == RELEASE_LABELS["7.3"]:
        return "7.3"
    return None


def release_key_from_meta(meta: Any) -> str | None:
    """cluster_meta.engine_release → 7.3 / 8 / None."""
    if not isinstance(meta, dict):
        return None
    return release_key_from_label(meta.get("engine_release"))


def load_compat(path: Path | None = None) -> dict[str, Any]:
    """Читает overlay; пустой dict если файла нет или JSON битый."""
    compat_path = path or COMPAT_PATH
    if not compat_path.exists():
        return {"tables": {}, "columns": {}}
    try:
        with open(compat_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"tables": {}, "columns": {}}
    return {
        "tables": data.get("tables") or {},
        "columns": data.get("columns") or {},
    }


def apply_compat(tables: dict[str, dict], compat: dict[str, Any]) -> None:
    """Навешивает since/until и column_compat на карточки (in-place)."""
    for table_name, spec in compat.get("tables", {}).items():
        if table_name not in tables or not isinstance(spec, dict):
            continue
        if spec.get("since"):
            tables[table_name]["since"] = spec["since"]
        if spec.get("until"):
            tables[table_name]["until"] = spec["until"]

    for qualified, spec in compat.get("columns", {}).items():
        if not isinstance(spec, dict) or "." not in qualified:
            continue
        table_name, _, column = qualified.partition(".")
        if table_name not in tables or not column:
            continue
        tables[table_name].setdefault("column_compat", {})[column] = spec


def _matches_release(since: str | None, until: str | None, release_key: str | None) -> bool:
    if release_key is None:
        return not since and not until
    if until:
        return release_key == until
    if since:
        return release_key == since
    return True


def table_visible_for_release(info: dict, release_key: str | None) -> bool:
    """Таблица видна для выбранного релиза (None — только общее)."""
    return _matches_release(info.get("since"), info.get("until"), release_key)


def visible_fields_doc(info: dict, release_key: str | None) -> dict[str, str]:
    """fields_doc без колонок чужого релиза."""
    fields_doc = info.get("fields_doc") or {}
    column_compat = info.get("column_compat") or {}
    visible: dict[str, str] = {}
    for field, desc in fields_doc.items():
        spec = column_compat.get(field) or {}
        if _matches_release(spec.get("since"), spec.get("until"), release_key):
            visible[field] = desc
    return visible


def filter_groups_for_release(
    groups: dict[str, dict[str, str]],
    release_key: str | None,
    compat: dict[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    """Убирает из превью таблицы since/until, не совпавшие с релизом дампа.

    Неизвестный релиз (None) не режет список: отсутствующие таблицы ловит превью.
    """
    if release_key is None:
        return groups
    table_specs = (compat if compat is not None else load_compat()).get("tables") or {}
    filtered: dict[str, dict[str, str]] = {}
    for group_name, tables in groups.items():
        kept = {
            name: desc
            for name, desc in tables.items()
            if table_visible_for_release(table_specs.get(name) or {}, release_key)
        }
        if kept:
            filtered[group_name] = kept
    return filtered


def release_badge_text(info: dict) -> str | None:
    """Подпись «только РЕД ВИРТ …» или None для общих таблиц."""
    key = info.get("since") or info.get("until")
    if not key:
        return None
    label = RELEASE_LABELS.get(str(key))
    return f"только {label}" if label else None


def load_changelog(path: Path | None = None) -> dict[str, Any]:
    """Читает замороженный diff 7.3/8; пустые списки если файла нет."""
    changelog_path = path or CHANGELOG_PATH
    empty: dict[str, Any] = {
        "tables_added": [],
        "tables_removed": [],
        "renames": [],
        "columns_removed": [],
        "columns_added": [],
        "columns_type": [],
    }
    if not changelog_path.exists():
        return empty
    try:
        with open(changelog_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return empty
    for key in empty:
        if not isinstance(data.get(key), list):
            data[key] = []
    return {**empty, **{k: data[k] for k in empty}}


def _code_names(names: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in names)


def _group_table_names(entries: list[dict], group: str) -> list[str]:
    names = [
        str(item["name"])
        for item in entries
        if isinstance(item, dict) and item.get("group") == group and item.get("name")
    ]
    return sorted(names)


def format_changelog_intro(changelog: dict[str, Any]) -> str:
    """Короткий changelog 7.3 → 8 по группам таблиц."""
    added = [item for item in changelog.get("tables_added") or [] if isinstance(item, dict)]
    removed = [item for item in changelog.get("tables_removed") or [] if isinstance(item, dict)]
    groups = sorted({str(item.get("group") or "Прочее") for item in added + removed})
    if not groups:
        return ""
    lines = [
        "В РЕД ВИРТ 8 относительно 7.3 изменилась схема таблиц:",
    ]
    for group in groups:
        new_names = _group_table_names(added, group)
        old_names = _group_table_names(removed, group)
        if old_names and new_names:
            lines.append(
                f"- **{group}**: вместо {_code_names(old_names)} — {_code_names(new_names)}."
            )
        elif new_names:
            verb = "добавлена" if len(new_names) == 1 else "добавлены"
            lines.append(f"- **{group}**: {verb} {_code_names(new_names)}.")
        elif old_names:
            lines.append(f"- **{group}**: нет в 8: {_code_names(old_names)}.")
    return "\n".join(lines)


def _qual_table_column(qualified: str) -> tuple[str, str] | None:
    table, sep, column = qualified.partition(".")
    if not sep or not table or not column:
        return None
    return table, column


def _column_changes_by_table(changelog: dict[str, Any]) -> dict[str, dict[str, list]]:
    """События по таблице: renames, removed, added, types."""
    rename_targets = {
        str(item["to"])
        for item in changelog.get("renames") or []
        if isinstance(item, dict) and item.get("to")
    }
    by_table: dict[str, dict[str, list]] = {}

    def bucket(table: str) -> dict[str, list]:
        return by_table.setdefault(
            table, {"renames": [], "removed": [], "added": [], "types": []}
        )

    for item in changelog.get("renames") or []:
        if not isinstance(item, dict) or not item.get("from") or not item.get("to"):
            continue
        parsed = _qual_table_column(str(item["from"]))
        if not parsed:
            continue
        table, old_col = parsed
        new_col = str(item["to"]).rsplit(".", 1)[-1]
        bucket(table)["renames"].append(
            {
                "old": old_col,
                "new": new_col,
                "from_type": item.get("from_type") or "",
                "to_type": item.get("to_type") or "",
            }
        )

    for item in changelog.get("columns_removed") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        parsed = _qual_table_column(str(item["name"]))
        if not parsed:
            continue
        table, column = parsed
        bucket(table)["removed"].append(column)

    for item in changelog.get("columns_added") or []:
        if not isinstance(item, dict) or not item.get("table") or not item.get("column"):
            continue
        table = str(item["table"])
        column = str(item["column"])
        if f"{table}.{column}" in rename_targets:
            continue
        bucket(table)["added"].append(column)

    for item in changelog.get("columns_type") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        parsed = _qual_table_column(str(item["name"]))
        if not parsed:
            continue
        table, column = parsed
        bucket(table)["types"].append(
            {
                "column": column,
                "from": item.get("from") or "?",
                "to": item.get("to") or "?",
            }
        )

    for data in by_table.values():
        data["removed"].sort()
        data["added"].sort()
        data["types"].sort(key=lambda row: row["column"])
    return by_table


def _code_tables(names: list[str]) -> str:
    codes = [f"`{item}`" for item in names]
    if not codes:
        return ""
    if len(codes) == 1:
        return codes[0]
    if len(codes) == 2:
        return f"{codes[0]} и {codes[1]}"
    return ", ".join(codes[:-1]) + f" и {codes[-1]}"


def _format_column_action_lines(changelog: dict[str, Any]) -> list[str]:
    """Фразы по таблицам: удалено / добавлено / переименовано; одинаковые смены типа склеиваются."""
    by_table = _column_changes_by_table(changelog)
    lines: list[str] = []

    for table in sorted(by_table):
        data = by_table[table]
        for rename in data["renames"]:
            old_t = rename["from_type"]
            new_t = rename["to_type"]
            left = f"`{rename['old']}`"
            if old_t:
                left += f" ({old_t})"
            right = f"`{rename['new']}`"
            if new_t:
                right += f" ({new_t})"
            if old_t and new_t and old_t != new_t:
                verb = "переименовано и изменён тип"
            else:
                verb = "переименовано"
            lines.append(f"- В `{table}` {verb}: {left} → {right}.")
        removed = data["removed"]
        if len(removed) == 1:
            lines.append(
                f"- В `{table}` удалено поле: `{removed[0]}`."
            )
        elif removed:
            lines.append(
                f"- В `{table}` удалены поля: {_code_names(removed)}."
            )
        added = data["added"]
        if len(added) == 1:
            lines.append(
                f"- В `{table}` добавлено поле: `{added[0]}`."
            )
        elif added:
            lines.append(
                f"- В `{table}` добавлены поля: {_code_names(added)}."
            )

    type_groups: dict[tuple[str, str, frozenset[str]], list[str]] = {}
    for table, data in by_table.items():
        if not data["types"]:
            continue
        by_sig: dict[tuple[str, str], list[str]] = {}
        for row in data["types"]:
            by_sig.setdefault((row["from"], row["to"]), []).append(row["column"])
        for (from_t, to_t), cols in by_sig.items():
            key = (from_t, to_t, frozenset(cols))
            type_groups.setdefault(key, []).append(table)

    for (from_t, to_t, cols) in sorted(
        type_groups, key=lambda item: (sorted(type_groups[item]), item[0], item[1])
    ):
        tables = sorted(type_groups[(from_t, to_t, cols)])
        col_list = sorted(cols)
        where = f"В {_code_tables(tables)}"
        if len(col_list) == 1:
            lines.append(
                f"- {where} изменён тип поля `{col_list[0]}` с {from_t} на {to_t}."
            )
        else:
            lines.append(
                f"- {where} изменён тип полей с {from_t} на {to_t}: {_code_names(col_list)}."
            )
    return lines


def format_changelog_details(changelog: dict[str, Any]) -> str:
    """Полный diff BASE TABLE атласа для expander."""
    sections: list[str] = []

    added = [item for item in changelog.get("tables_added") or [] if isinstance(item, dict)]
    removed = [item for item in changelog.get("tables_removed") or [] if isinstance(item, dict)]
    groups = sorted({str(item.get("group") or "Прочее") for item in added + removed})

    only_8_lines = []
    only_73_lines = []
    for group in groups:
        new_names = _group_table_names(added, group)
        old_names = _group_table_names(removed, group)
        if new_names:
            only_8_lines.append(f"- **{group}**: {_code_names(new_names)}")
        if old_names:
            only_73_lines.append(f"- **{group}**: {_code_names(old_names)}")
    if only_8_lines:
        sections.append("**Таблицы только в РЕД ВИРТ 8**\n" + "\n".join(only_8_lines))
    if only_73_lines:
        sections.append("**Таблицы только в РЕД ВИРТ 7.3**\n" + "\n".join(only_73_lines))

    col_lines = _format_column_action_lines(changelog)
    if col_lines:
        sections.append(
            "**Изменения в РЕД ВИРТ 8**\n" + "\n".join(col_lines)
        )

    return "\n\n".join(sections)


def field_compat_note(spec: dict | None) -> str:
    """Короткая пометка версии и переименования для поля."""
    if not spec:
        return ""
    parts: list[str] = []
    key = spec.get("since") or spec.get("until")
    if key and key in RELEASE_LABELS:
        parts.append(f"только {RELEASE_LABELS[key]}")
    successor = spec.get("successor")
    if successor:
        parts.append(f"в 8: `{str(successor).rsplit('.', 1)[-1]}`")
    predecessor = spec.get("predecessor")
    if predecessor:
        parts.append(f"в 7.3: `{str(predecessor).rsplit('.', 1)[-1]}`")
    return " · ".join(parts)


def load_atlas_data() -> dict:
    """
    Загружает данные из всех JSON-файлов в директории ATLAS_DIR.

    Returns:
        Словарь вида {"tables": {table_name: metadata}}
    """
    if "atlas_data" not in st.session_state:
        all_tables: dict[str, dict] = {}

        if not ATLAS_DIR.exists():
            st.warning(f"Директория {ATLAS_DIR} не найдена. Проверьте структуру проекта.")
            return {"tables": {}}

        json_files = sorted(ATLAS_DIR.glob("*.json"))

        if not json_files:
            st.warning(f"В директории {ATLAS_DIR} не найдено JSON-файлов справочника.")
            return {"tables": {}}

        for file_path in json_files:
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)

                if "tables" in data:
                    group_name = data.get("group", "Uncategorized")
                    tables = data["tables"]

                    for table_name, metadata in tables.items():
                        if table_name in all_tables:
                            st.warning(
                                f"⚠️ Обнаружен дубликат таблицы '{table_name}' "
                                f"в файле {file_path.name}. Пропускаю."
                            )
                            continue

                        metadata["group"] = group_name
                        all_tables[table_name] = metadata

            except json.JSONDecodeError:
                st.error(f"Ошибка чтения JSON файла: {file_path.name}")
            except Exception as exc:
                st.error(f"Неожиданная ошибка при обработке {file_path.name}: {exc}")

        apply_compat(all_tables, load_compat())
        st.session_state["atlas_data"] = {"tables": all_tables}

    return st.session_state["atlas_data"]

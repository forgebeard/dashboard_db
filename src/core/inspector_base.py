# src/core/inspector_base.py
"""
Базовая абстракция для SQL-инспекторов oVirt Engine.

Унифицирует подключение к БД через SQLAlchemy, заменяет прямой psycopg2,
предоставляет общие хелперы форматирования и контекстный менеджер
для автоматического управления ресурсами.
"""

from __future__ import annotations

import logging  # Логирование жизненного цикла соединений
from datetime import datetime  # Работа с датой/временем для хелперов форматирования
from typing import Any  # Type hints для универсальных параметров

from sqlalchemy import text  # Параметризованные запросы с :param синтаксисом
from sqlalchemy.engine import Engine  # Тип движка SQLAlchemy для type hints
from sqlalchemy.sql.expression import (
    TextClause,  # Тип для проверки готовых SQL-объектов
)

from core.db_utils import (
    get_sqlalchemy_engine,  # Единая точка получения кэшированного движка
)
from core.exceptions import DataLoadError, format_load_error

logger = logging.getLogger(__name__)


class InspectorBase:
    """
    Базовый класс для всех инспекторов дампов PostgreSQL oVirt Engine.

    Используется как контекстный менеджер для гарантированного освобождения
    соединений. Предоставляет параметризованные запросы через sqlalchemy.text()
    и общие утилиты форматирования.

    Пример использования:
        with InspectorBase("engine_dump_2024") as insp:
            # Простой строковый запрос
            row = insp.fetch_one("SELECT * FROM vds WHERE vds_id = :id", {"id": vds_id})
            rows = insp.fetch_all("SELECT * FROM storage_domains")

            # Готовый TextClause с expanding IN (для динамических списков)
            from sqlalchemy import bindparam
            stmt = text("SELECT * FROM vds WHERE vds_id IN (:ids)").bindparams(
                bindparam("ids", expanding=True)
            )
            rows = insp.fetch_all(stmt, {"ids": ["uuid1", "uuid2"]})
    """

    def __init__(self, db_name: str) -> None:
        """
        Инициализация инспектора.

        Args:
            db_name: Имя базы данных (дампа) для подключения.
                     Нормализуется внутри get_sqlalchemy_engine().
        """
        self._db_name = db_name
        self._engine: Engine | None = None  # Ссылка на кэшированный движок
        self._conn = None                   # Активное соединение (открывается в __enter__)

    def __enter__(self) -> InspectorBase:
        """
        Открывает соединение при входе в контекст.

        Движок получается из кэша st.cache_resource — повторные вызовы
        для той же БД не создают новых пулов соединений.
        """
        self._engine = get_sqlalchemy_engine(self._db_name)
        self._conn = self._engine.connect()
        logger.debug("Соединение инспектора для '%s' открыто", self._db_name)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Закрывает соединение при выходе из контекста.

        Engine НЕ диспозится — он кэшируется через st.cache_resource в db_utils.
        Диспоз кэшированного движка сломал бы все остальные компоненты приложения.
        Закрывается только соединение (connection), которое возвращает слот в пул.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        logger.debug("Соединение инспектора для '%s' закрыто", self._db_name)

    def fetch_one(self, sql: str | TextClause, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """
        Выполняет запрос и возвращает одну строку как словарь.

        Args:
            sql: SQL-запрос в одном из двух форматов:
                 - Строка с именованными параметрами (:param) — будет обёрнута в text()
                 - Готовый TextClause (например, с bindparam expanding=True) — используется как есть
            params: Словарь параметров запроса.

        Returns:
            Словарь с данными строки или None, если результат пуст.

        Raises:
            RuntimeError: Если вызван вне контекстного менеджера (with).
        """
        if self._conn is None:
            raise RuntimeError("InspectorBase должен использоваться внутри контекстного менеджера (with)")

        stmt = sql if isinstance(sql, TextClause) else text(sql)
        try:
            result = self._conn.execute(stmt, params or {})
        except DataLoadError:
            raise
        except Exception as exc:
            raise DataLoadError(format_load_error(exc)) from exc
        # .mappings() гарантирует возврат строк как словарей (аналог RealDictCursor)
        row = result.mappings().fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str | TextClause, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Выполняет запрос и возвращает все строки как список словарей.

        Args:
            sql: SQL-запрос в одном из двух форматов:
                 - Строка с именованными параметрами (:param) — будет обёрнута в text()
                 - Готовый TextClause (например, с bindparam expanding=True) — используется как есть
            params: Словарь параметров запроса.

        Returns:
            Список словарей. Пустой список, если результат пуст.

        Raises:
            RuntimeError: Если вызван вне контекстного менеджера (with).
        """
        if self._conn is None:
            raise RuntimeError("InspectorBase должен использоваться внутри контекстного менеджера (with)")

        stmt = sql if isinstance(sql, TextClause) else text(sql)
        try:
            result = self._conn.execute(stmt, params or {})
        except DataLoadError:
            raise
        except Exception as exc:
            raise DataLoadError(format_load_error(exc)) from exc
        return [dict(row) for row in result.mappings().fetchall()]

    # ─── Общие хелперы форматирования ────────────────────────────────
    # Эти методы покрывают типовые потребности инспекторов oVirt.
    # Специфичные для конкретного инспектора хелперы остаются в его модуле.

    @staticmethod
    def fmt_date(value: Any, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        """
        Форматирует дату/время для отображения в отчётах.

        Args:
            value: Объект datetime, строка или None.
            fmt: Формат вывода strftime.

        Returns:
            Отформатированная строка или "N/A" при отсутствии значения.
        """
        if value is None:
            return "N/A"
        if isinstance(value, datetime):
            return value.strftime(fmt)
        return str(value)

    @staticmethod
    def fmt_size_gb(value: Any, precision: int = 2) -> str:
        """
        Форматирует размер в байтах в гигабайты для отображения.

        Args:
            value: Размер в байтах (int/float/str) или None.
            precision: Количество знаков после запятой.

        Returns:
            Строка вида "123.45 GB" или "N/A".
        """
        if value is None:
            return "N/A"
        try:
            gb = float(value) / (1024 ** 3)
            return f"{gb:.{precision}f} GB"
        except (ValueError, TypeError):
            return "N/A"

    @staticmethod
    def fmt_status(status_code: Any, status_map: dict[int, str]) -> str:
        """
        Маппит числовой код статуса в человекочитаемую строку.

        Args:
            status_code: Числовой код статуса из БД.
            status_map: Словарь маппинга {код: описание}.

        Returns:
            Описание статуса или "Unknown (<code>)".
        """
        if status_code is None:
            return "N/A"
        try:
            code = int(status_code)
        except (ValueError, TypeError):
            return f"Invalid ({status_code})"
        return status_map.get(code, f"Unknown ({code})")
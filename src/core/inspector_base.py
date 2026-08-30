# src/core/inspector_base.py
"""Контекст SQL-инспектора: соединение и fetch_one / fetch_all."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.expression import (
    TextClause,
)

from core.db_utils import (
    get_sqlalchemy_engine,
)
from core.exceptions import DataLoadError, wrap_load_error

logger = logging.getLogger(__name__)
T = TypeVar("T")


class InspectorBase:
    """Контекстный менеджер соединения и параметризованные запросы."""

    def __init__(self, db_name: str) -> None:
        """Имя дампа; движок берётся из get_sqlalchemy_engine."""
        self._db_name = db_name
        self._engine: Engine | None = None
        self._conn = None

    @staticmethod
    def _wrap_driver(fn: Callable[[], T]) -> T:
        try:
            return fn()
        except DataLoadError:
            raise
        except Exception as exc:
            raise wrap_load_error(exc) from exc

    def __enter__(self) -> InspectorBase:
        """Открывает соединение (движок кэшируется)."""
        def _open() -> None:
            self._engine = get_sqlalchemy_engine(self._db_name)
            self._conn = self._engine.connect()

        self._wrap_driver(_open)
        logger.debug("Соединение инспектора для '%s' открыто", self._db_name)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Возвращает соединение в пул; engine не диспозится."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                logger.warning(
                    "Не удалось закрыть соединение инспектора для '%s'",
                    self._db_name,
                    exc_info=True,
                )
            finally:
                self._conn = None
        logger.debug("Соединение инспектора для '%s' закрыто", self._db_name)

    def fetch_one(self, sql: str | TextClause, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Одна строка-словарь или None. Только внутри with."""
        if self._conn is None:
            raise RuntimeError("InspectorBase должен использоваться внутри контекстного менеджера (with)")

        stmt = sql if isinstance(sql, TextClause) else text(sql)
        result = self._wrap_driver(lambda: self._conn.execute(stmt, params or {}))
        row = result.mappings().fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str | TextClause, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Все строки как список словарей. Только внутри with."""
        if self._conn is None:
            raise RuntimeError("InspectorBase должен использоваться внутри контекстного менеджера (with)")

        stmt = sql if isinstance(sql, TextClause) else text(sql)
        result = self._wrap_driver(lambda: self._conn.execute(stmt, params or {}))
        return [dict(row) for row in result.mappings().fetchall()]

# src/core/inspector_base.py
"""
Базовая абстракция для SQL-инспекторов oVirt Engine.

Контекстный менеджер соединения и параметризованные fetch_one / fetch_all.
"""

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
    """
    Базовый класс для всех инспекторов дампов PostgreSQL oVirt Engine.

    Используется как контекстный менеджер для гарантированного освобождения
    соединений. Предоставляет параметризованные запросы через sqlalchemy.text().

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

    @staticmethod
    def _wrap_driver(fn: Callable[[], T]) -> T:
        try:
            return fn()
        except DataLoadError:
            raise
        except Exception as exc:
            raise wrap_load_error(exc) from exc

    def __enter__(self) -> InspectorBase:
        """
        Открывает соединение при входе в контекст.

        Движок получается из кэша st.cache_resource — повторные вызовы
        для той же БД не создают новых пулов соединений.
        """
        def _open() -> None:
            self._engine = get_sqlalchemy_engine(self._db_name)
            self._conn = self._engine.connect()

        self._wrap_driver(_open)
        logger.debug("Соединение инспектора для '%s' открыто", self._db_name)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Закрывает соединение при выходе из контекста.

        Engine НЕ диспозится — он кэшируется через st.cache_resource в db_utils.
        Диспоз кэшированного движка сломал бы все остальные компоненты приложения.
        Закрывается только соединение (connection), которое возвращает слот в пул.
        Сбой close логируется и не подменяет исключение тела with.
        """
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
        result = self._wrap_driver(lambda: self._conn.execute(stmt, params or {}))
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
        result = self._wrap_driver(lambda: self._conn.execute(stmt, params or {}))
        return [dict(row) for row in result.mappings().fetchall()]

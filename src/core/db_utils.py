# src/core/db_utils.py
"""
Модуль инфраструктуры подключения к БД.

Отвечает за: создание/кэширование движка SQLAlchemy, получение списка доступных дампов 
и служебные запросы (список таблиц). Не содержит бизнес-логики.
Является единой точкой входа для всех SQL-операций в проекте.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import logging  # Логирование ошибок и событий подключения
import os  # Чтение переменных окружения (.env) для параметров подключения

import pandas as pd
import psycopg2  # Драйвер PostgreSQL для служебных запросов (системные таблицы)
import streamlit as st  # Декоратор кэширования ресурсов (@st.cache_resource)
from dotenv import (
    load_dotenv,  # Загрузка переменных из файла .env перед чтением через os.getenv
)

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
from sqlalchemy import (  # Создание DB-движка, безопасный SQL и конструктор URL
    URL,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.sql.expression import TextClause

from core.config import statement_timeout_ms
from core.exceptions import DataLoadError, wrap_load_error

load_dotenv()
logger = logging.getLogger(__name__)

# Глобальные настройки подключения
DB_SCHEMA = "public"              # Схема по умолчанию для oVirt Engine
CONNECT_TIMEOUT = 10              # Таймаут соединения в секундах
ENGINE_CACHE_MAXSIZE = 8          # Максимум кэшированных движков (для локальных дампов достаточно)


def pg_read_only_options() -> str:
    """options libpq: read-only + statement_timeout из env на момент вызова."""
    return (
        "-c default_transaction_read_only=on "
        f"-c statement_timeout={statement_timeout_ms()}ms"
    )


def get_db_params(db_name: str | None = None) -> dict[str, str | int]:
    """
    Собирает параметры подключения из .env с валидацией обязательных полей.
    
    Args:
        db_name: Имя целевой базы данных. Если None, берется из DB_NAME
        
    Returns:
        Словарь параметров подключения (порт уже преобразован в int)
        
    Raises:
        ValueError: Если не задан обязательный параметр DB_PASSWORD
    """
    password = os.getenv("DB_PASSWORD")
    if not password:
        raise ValueError(
            "Не задан пароль для БД. Проверьте наличие DB_PASSWORD в файле .env"
        )
        
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": db_name or os.getenv("DB_NAME", "postgres"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": password,
        "options": pg_read_only_options(),
    }


def get_psycopg2_connect_kwargs(db_name: str | None = None) -> dict:
    """Параметры psycopg2.connect: те же, что get_db_params, плюс таймаут."""
    params = get_db_params(db_name)
    return {**params, "connect_timeout": CONNECT_TIMEOUT}


@st.cache_resource(max_entries=ENGINE_CACHE_MAXSIZE)
def get_sqlalchemy_engine(db_name: str):
    """
    Возвращает кэшированный движок SQLAlchemy с безопасным формированием URL.
    
    Используется st.cache_resource вместо lru_cache для корректной интеграции 
    с жизненным циклом Streamlit (очистка при рестарте сервера).
    Имя БД нормализуется к нижнему регистру для предотвращения дублирования кэша.
    Возвращённый Engine нельзя dispose(): это уничтожит общий пул для всего приложения.
    Смена STATEMENT_TIMEOUT_MS в env применяется к новым движкам; уже закэшированный
    engine сохраняет options до рестарта приложения.
    
    Args:
        db_name: Имя базы данных (дампа)
        
    Returns:
        Объект sqlalchemy.engine.Engine
    """
    try:
        # Нормализация имени БД для корректного кэширования
        normalized_name = db_name.lower().strip()

        params = get_db_params(normalized_name)

        # Безопасное формирование URL с автоматическим экранированием спецсимволов в пароле
        db_url = URL.create(
            drivername="postgresql+psycopg2",
            username=params["user"],
            password=params["password"],
            host=params["host"],
            port=params["port"],
            database=params["dbname"]
        )

        logger.info(f"Создание/получение движка для БД: {params['dbname']}")

        return create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": CONNECT_TIMEOUT,
                "options": pg_read_only_options(),
            },
            pool_size=5,
            max_overflow=10,
        )
    except DataLoadError:
        raise
    except Exception as exc:
        raise wrap_load_error(exc) from exc


def read_sql_df(
    engine: Engine,
    sql: str | TextClause,
    params: dict | None = None,
) -> pd.DataFrame:
    """Выполняет SELECT и при ошибке драйвера/таймауте поднимает DataLoadError."""
    try:
        stmt = sql if isinstance(sql, TextClause) else text(sql)
        return pd.read_sql(stmt, engine, params=params)
    except DataLoadError:
        raise
    except Exception as exc:
        raise wrap_load_error(exc) from exc


def load_sql_df(
    db_name: str,
    sql: str | TextClause,
    params: dict | None = None,
) -> pd.DataFrame:
    """Движок по имени БД + read_sql_df."""
    return read_sql_df(get_sqlalchemy_engine(db_name), sql, params)


def get_available_databases() -> list[str]:
    """
    Получает список доступных БД через psycopg2 (быстрее для системных запросов).
    Использует контекстный менеджер для гарантированного закрытия соединения.

    Returns:
        Список имен баз данных. Пустой список, если каталог успешно прочитан и пуст.

    Raises:
        DataLoadError: Если не удалось подключиться ни к postgres, ни к template1.
    """
    system_dbs = ["postgres", "template1"]
    last_exc: Exception | None = None

    for sys_db in system_dbs:
        try:
            params = get_psycopg2_connect_kwargs(sys_db)
            with psycopg2.connect(**params) as conn, conn.cursor() as cur:
                cur.execute("""
                        SELECT datname FROM pg_database 
                        WHERE datistemplate = false AND datallowconn = true 
                        ORDER BY datname;
                    """)
                return [row[0] for row in cur.fetchall()]
        except ValueError:
            raise
        except Exception as e:
            last_exc = e
            logger.debug(f"Не удалось подключиться к '{sys_db}': {e}")
            continue

    logger.warning("Не удалось получить список БД ни через postgres, ни через template1")
    if last_exc is None:
        raise DataLoadError("Не удалось получить список баз данных")
    raise wrap_load_error(last_exc) from last_exc


def get_table_list(db_name: str, schema: str = DB_SCHEMA) -> list[str]:
    """
    Возвращает список пользовательских таблиц в указанной схеме БД.

    Args:
        db_name: Имя базы данных
        schema: Имя схемы (по умолчанию 'public')

    Returns:
        Отсортированный список имен таблиц.

    Raises:
        DataLoadError: Если движок или запрос к information_schema не удались.
    """
    try:
        engine = get_sqlalchemy_engine(db_name)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = :schema AND table_type = 'BASE TABLE'
                ORDER BY table_name;
            """), {"schema": schema})
            return [row[0] for row in result.fetchall()]
    except DataLoadError:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения списка таблиц для {db_name}: {e}")
        raise wrap_load_error(e) from e
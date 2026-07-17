# src/core/db_utils.py
"""
Модуль инфраструктуры подключения к БД.

Отвечает за: создание/кэширование движка SQLAlchemy, получение списка доступных дампов 
и служебные запросы (список таблиц). Не содержит бизнес-логики.
Является единой точкой входа для всех SQL-операций в проекте.
"""

# --- СТАНДАРТНЫЕ БИБЛИОТЕКИ ---
import os               # Чтение переменных окружения (.env) для параметров подключения
import logging          # Логирование ошибок и событий подключения

# --- СТОРОННИЕ БИБЛИОТЕКИ ---
from sqlalchemy import create_engine, text, URL  # Создание DB-движка, безопасный SQL и конструктор URL
from dotenv import load_dotenv   # Загрузка переменных из файла .env перед чтением через os.getenv
import psycopg2                  # Драйвер PostgreSQL для служебных запросов (системные таблицы)
import streamlit as st           # Декоратор кэширования ресурсов (@st.cache_resource)

load_dotenv()
logger = logging.getLogger(__name__)

# Глобальные настройки подключения
DB_SCHEMA = "public"              # Схема по умолчанию для oVirt Engine
CONNECT_TIMEOUT = 10              # Таймаут соединения в секундах
ENGINE_CACHE_MAXSIZE = 8          # Максимум кэшированных движков (для локальных дампов достаточно)


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
    }


@st.cache_resource(max_entries=ENGINE_CACHE_MAXSIZE)
def get_sqlalchemy_engine(db_name: str):
    """
    Возвращает кэшированный движок SQLAlchemy с безопасным формированием URL.
    
    Используется st.cache_resource вместо lru_cache для корректной интеграции 
    с жизненным циклом Streamlit (очистка при рестарте сервера).
    Имя БД нормализуется к нижнему регистру для предотвращения дублирования кэша.
    
    Args:
        db_name: Имя базы данных (дампа)
        
    Returns:
        Объект sqlalchemy.engine.Engine
    """
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
        pool_pre_ping=True,           # Проверка живости соединения перед каждым запросом
        connect_args={"connect_timeout": CONNECT_TIMEOUT},  # Явный таймаут подключения
        pool_size=5,                    # Размер пула соединений
        max_overflow=10                 # Максимум дополнительных соединений
    )


def get_available_databases() -> list[str]:
    """
    Получает список доступных БД через psycopg2 (быстрее для системных запросов).
    Использует контекстный менеджер для гарантированного закрытия соединения.
    
    Returns:
        Список имен баз данных. Пустой список при ошибке подключения.
    """
    system_dbs = ["postgres", "template1"]
    
    for sys_db in system_dbs:
        try:
            params = get_db_params(sys_db)
            with psycopg2.connect(**params, connect_timeout=CONNECT_TIMEOUT) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT datname FROM pg_database 
                        WHERE datistemplate = false AND datallowconn = true 
                        ORDER BY datname;
                    """)
                    dbs = [row[0] for row in cur.fetchall()]
                    return dbs
        except Exception as e:
            logger.debug(f"Не удалось подключиться к '{sys_db}': {e}")
            continue
            
    logger.warning("Не удалось получить список БД ни через postgres, ни через template1")
    return []


def get_table_list(db_name: str, schema: str = DB_SCHEMA) -> list[str]:
    """
    Возвращает список пользовательских таблиц в указанной схеме БД.
    Используется для автодополнения в SQL-редакторе.
    
    Args:
        db_name: Имя базы данных
        schema: Имя схемы (по умолчанию 'public')
        
    Returns:
        Отсортированный список имен таблиц. Пустой список при ошибке.
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
    except Exception as e:
        logger.error(f"Ошибка получения списка таблиц для {db_name}: {e}")
        return []
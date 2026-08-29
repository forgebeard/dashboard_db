# RED Virt Analytics

Дашборд для диагностики БД oVirt Engine. Инструмент предназначен для инженеров L2/L3 поддержки РЕД СОФТ. Позволяет проводить глубокий анализ локальных дампов PostgreSQL без риска воздействия на продуктивную среду.

## Особенности

-   **Глубокая диагностика:** Встроенные инспекторы (Host/VM Inspector) собирают полный отчет о состоянии объекта.
-   **Безопасность:** Работа строго оффлайн с локальными копиями БД. Отсутствие исходящих соединений.
-   **Производительность:** Лимиты строк, фильтрация на уровне SQL и оптимизированные запросы.
-   **Интерфейс:** Выбор раздела в сайдбаре (на rerun выполняется только активный модуль), каскадные фильтры (ДЦ -> Кластер -> Хост), цветовая индикация статусов, экспорт в CSV.
-   **Модульность:** Разделение логики данных, интерфейса и диагностических утилит.
-   **Контейнеризация:** Запуск через Docker — никаких зависимостей Python на хосте.

## Технический стек

| Компонент | Технология | Назначение |
| :--- | :--- | :--- |
| Frontend | Streamlit | Веб-интерфейс и визуализация |
| Backend | Python 3.11+ | Логика приложения |
| Database | PostgreSQL (Psycopg2 / SQLAlchemy) | Подключение к дампу oVirt Engine |
| Data | Pandas | Обработка табличных данных |
| Runtime | Docker / Docker Compose | Изоляция и переносимость |
| OS | RED OS 8 (KDE) / Windows | Целевые платформы |

## Быстрый старт

Нужны Docker (Compose) и PostgreSQL с восстановленным дампом. ОС не важна: Linux, macOS и Windows запускаются одинаково через `./start.sh` или `start.bat`. Python на хост ставить не нужно.

### 1. Восстановление дампа

Дашборд читает дамп (или доступную PostgreSQL), не пишет в Engine. Режим правок и скриптов для заказчика — в разработке.

В DBeaver подключитесь к локальному PostgreSQL (`localhost`).

1. ПКМ на «Databases» → «Create New Database». Имя, например `ovirt_diag`, владелец — ваш пользователь Postgres.
2. ПКМ на созданной базе → **Tools** → **Restore**. Выберите `.dump` или `.sql`.
3. Включите **Do not save owner** и **Do not save privileges**. **Start**, дождитесь успеха.

Подключение дашборда настраивается скриптом запуска (`DB_HOST=host.docker.internal` из контейнера), а не ручным `.env` с `localhost`.

### 2. Запуск

**Linux / macOS:** `./start.sh`  
**Windows:** `start.bat`

При первом запуске скрипт спросит параметры и соберёт контейнер.

| Параметр | По умолчанию | Описание |
|---|---|---|
| `DB_HOST` | `host.docker.internal` | Postgres на той же машине, что Docker |
| `DB_PORT` | `5432` | Порт PostgreSQL |
| `DB_NAME` | `engine` | Имя базы с дампом |
| `DB_USER` | `postgres` | Пользователь БД |
| `DB_PASSWORD` | — | Пароль (обязательно) |

Откройте **http://localhost:8502**

**Управление**

```bash
./start.sh              # Запуск / перезапуск (Linux/macOS)
./start.sh -r           # Перенастроить .env
start.bat               # То же на Windows
start.bat -r
docker compose down     # Остановить
docker compose logs -f  # Логи контейнера
```

### 3. Если контейнер не видит PostgreSQL (Linux)

На Linux Postgres часто слушает только `127.0.0.1`, а контейнер ходит на хост с адреса docker-моста. Windows / Docker Desktop: этот раздел обычно не нужен, если Postgres слушает `0.0.0.0` и `host.docker.internal` резолвится.

Разрешить прослушивание (путь к data dir может отличаться):

```bash
sudo sed -i "s/^#*listen_addresses.*/listen_addresses = '*'/" \
  /var/lib/pgsql/15/data/postgresql.conf
sudo systemctl restart postgresql-15
ss -tlnp | grep 5432
# Ожидается: 0.0.0.0:5432
```

`listen_addresses = '*'` означает, что порт 5432 слушает **все интерфейсы хоста**. Ограничение доступа — файрвол и `pg_hba.conf`.

Пример строки `pg_hba` (метод `md5`, как часто уже настроено; пароль Postgres не перевыпускать ради scram):

```bash
echo "host    all    all    172.16.0.0/12    md5" | \
  sudo tee -a /var/lib/pgsql/15/data/pg_hba.conf
sudo systemctl reload postgresql-15
```

`172.16.0.0/12` — широкий диапазон частных адресов (в том числе типичные сети Docker), **не** «только Docker». Клиенты из интернета в этот CIDR не входят, поэтому этой строкой снаружи не пускаются. Адреса LAN/VPN из того же `/12` — пускаются. Не копируйте эту строку на Windows как обязательный шаг.

### Если БД на удалённом сервере

В `start.sh` / `start.bat` (или `.env`) укажите IP сервера вместо `host.docker.internal`, затем `-r` если `.env` уже был. На удалённом Postgres должны быть разрешены подключения **с того адреса, с которого выходит Docker-хост** (не «docker-подсеть ноутбука»). Настройка listen/`pg_hba` — на стороне того сервера, в его дистрибутиве, не через `sed` из этого README как универсальный рецепт.

## CI

При push и pull request GitHub Actions запускает `ruff check`, unit-тесты pytest (без интеграционных, им нужна живая БД) и сборку Docker-образа. Чтобы красный CI блокировал merge, включите required checks в настройках ветки на GitHub.

## Структура проекта

Архитектура основана на принципе SRP. Функциональные модули унифицированы: `module` (UI), `utils` (SQL/Logic), `diagnostics` (Raw Tables).

```text
.
├── Dockerfile                  # Сборка Docker-образа
├── docker-compose.yml          # Оркестрация контейнера
├── start.sh                    # Интерактивный запуск и настройка (Linux/macOS)
├── start.bat                   # Интерактивный запуск и настройка (Windows)
├── ruff.toml                   # Узкий линт (E, F, I)
├── .github/workflows/ci.yml    # ruff, pytest, docker build
├── .env.example                # Шаблон переменных окружения
├── requirements.txt            # Runtime-зависимости Python
├── requirements-dev.txt        # pytest, ruff (не ставятся в Docker-образ)
│
└── src/
    ├── app.py                  # Точка входа: маршрутизация вкладок
    ├── core/                   # Базовые утилиты ядра
    │   ├── config.py           # Глобальные настройки (лимиты, CSS)
    │   ├── constants.py        # Справочники статусов (VM/HOST_STATUS_MAP)
    │   ├── db_utils.py         # Движок подключения к БД
    │   ├── data_loader.py      # Загрузка метаданных инфраструктуры
    │   ├── sql_editor.py       # Компонент глобального SQL-редактора
    │   └── ui_utils.py         # Утилиты UI (форматирование UUID, дат)
    │
    ├── vms/                    # Модуль Виртуальных машин
    │   ├── vms_module.py       # UI: список, фильтры, инспектор
    │   ├── vms_utils.py        # Логика: SQL-запросы, маппинги
    │   ├── vms_diagnostics.py  # Просмотр таблиц vm_static/dynamic
    │   └── vm_inspector_sql.py # Отчет по ВМ (диски, сеть, снапшоты)
    │
    ├── hosts/                  # Модуль Хостов
    │   ├── hosts_module.py     # UI: список хостов, фильтры
    │   ├── hosts_utils.py      # Логика: запросы к vds_static/dynamic
    │   ├── hosts_diagnostics.py# Таблицы хостов и интерфейсов
    │   └── host_inspector_sql.py # Отчет по хосту (CPU, RAM, Storage)
    │
    ├── storage/                # Модуль Хранилищ
    │   ├── storage_module.py   # UI: список Storage Domains
    │   ├── storage_utils.py    # Логика: связи SD <-> DC <-> Hosts
    │   └── storage_diagnostics.py # Таблицы storage_domains, luns
    │
    ├── clusters/               # Модуль Кластеров
    │   ├── clusters_module.py  # UI: список кластеров, версии
    │   ├── clusters_utils.py   # Логика: параметры, scheduling policy
    │   └── clusters_diagnostics.py # Таблицы cluster, cluster_policy
    │
    ├── networks/               # Модуль Сетей
    │   ├── network_module.py   # UI: логические сети, vNIC profiles
    │   ├── network_utils.py    # Логика: маппинг сетей на хосты
    │   └── network_diagnostics.py # Таблицы network, vnic_profiles
    │
    ├── disks/                  # Модуль Дисков и Образов
    │   ├── disks_module.py     # UI: список дисков, форматы
    │   ├── disks_utils.py      # Логика: Disk <-> Image <-> Volume
    │   └── disks_diagnostics.py # Таблицы images, image_group_map
    │
    ├── snapshots/              # Модуль Снапшотов
    │   ├── snapshots_module.py # UI: дерево снапшотов, статусы
    │   ├── snapshots_utils.py  # Логика: цепочки снапшотов
    │   └── snapshots_diagnostics.py # Таблицы snapshots, child_map
    │
    ├── gluster/                # Модуль GlusterFS
    │   ├── gluster_module.py   # UI: тома, брики, статусы
    │   ├── gluster_utils.py    # Логика: мониторинг Gluster
    │   └── gluster_diagnostics.py # Таблицы gluster_volumes_services
    │
    ├── tasks/                  # Модуль Асинхронных задач
    │   ├── tasks_module.py     # UI: список Jobs, шаги
    │   ├── tasks_utils.py      # Логика: поиск зависших задач
    │   └── tasks_diagnostics.py # Таблицы job, step
    │
    ├── audit/                  # Модуль Журнала событий
    │   ├── audit_module.py     # UI: фильтр событий, таймлайн
    │   ├── audit_utils.py      # Логика: агрегация ошибок
    │   └── audit_diagnostics.py # Таблица audit_log (с LIMIT)
    │
    ├── users/                  # Модуль Пользователей и прав
    │   ├── users_module.py     # UI: пользователи, роли, проекты
    │   ├── users_utils.py      # Логика: RBAC проверки
    │   └── users_diagnostics.py # Таблицы users, permissions
    │
    ├── system/                 # Системные таблицы
    │   ├── system_module.py    # UI: общие настройки engine
    │   └── system_utils.py     # Логика: конфигурационные ключи
    │
    ├── cert/                   # Модуль Сертификатов PKI
    │   └── certificates.py     # Проверка сроков действия CA/Host
    │
    └── atlas/                  # Справочник схемы БД
        ├── atlas_module.py     # Интерактивная карта таблиц oVirt
        ├── data_loader.py      # Загрузка JSON-метаданных схемы
        └── renderer.py         # Отрисовка графа связей
```

## Руководство по модулям

### Хосты и ВМ
-   **Список:** Поиск по имени/FQDN, фильтрация по кластерам, выделение проблемных узлов.
-   **Инспектор:** Текстовый отчет со статусами, ресурсами, сетью и аудиторскими событиями.
-   **Диагностика:** Прямой просмотр системных таблиц (`vds_static`, `vm_dynamic`) с защитой от переполнения памяти.

### Сети и Хранилища
-   Анализ логических сетей, vNIC профилей и состояния Storage Domains.
-   Проверка связей между хранилищами и дата-центрами, поиск несоответствий LUN.

### Задачи и Аудит
-   Мониторинг зависших задач (Jobs) и анализ журнала событий (Audit Log).
-   Выявление причин сбоев через корреляцию задач и логов.

## Безопасность и ограничения

1.  **Конфиденциальность:** Дампы БД содержат чувствительные данные. Храните их в защищенном месте.
2.  **Память:** При работе с `audit_log` или `event_history` используйте фильтр по дате. Выборка автоматически ограничена, но требует внимания при ручных запросах.
3.  **Локальный контур:** `docker-compose` публикует порт только на `127.0.0.1:8502`. С LAN и других интерфейсов хоста UI недоступен. Внутри контейнера Streamlit слушает `0.0.0.0:8501` — это нужно для проброса порта, не для внешнего доступа.
4.  **Режим чтения:** Каждое подключение к PostgreSQL открывается с `default_transaction_read_only=on`. SQL-редактор принимает только SELECT/WITH (и EXPLAIN к ним), несколько стейтментов запрещены, выборка ограничена `MAX_ROW_LIMIT`. DML отклоняется и фильтром редактора, и самой БД.

---
*Разработано для нужд технической поддержки виртуализации РЕД СОФТ.*

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

Если контейнер уже был запущен со старым именем (`ovirt-dump-analyzer` / сервис `ovirt-analyzer`), сначала `docker compose down`, затем снова `./start.sh` (или `start.bat`).

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

При push и pull request GitHub Actions запускает `ruff check`, сверку `uv export` с `requirements*.txt`, unit-тесты pytest с покрытием `src` (без интеграционных) и сборку Docker-образа. Чтобы красный CI блокировал merge, включите required checks в настройках ветки на GitHub.

## Структура проекта

Архитектура основана на принципе SRP. Функциональные модули унифицированы: `module` (UI), `utils` (SQL/Logic), `diagnostics` (Raw Tables).

```text
.
├── Dockerfile
├── docker-compose.yml          # сервис и контейнер: red-virt-analytics
├── start.sh / start.bat
├── pyproject.toml              # name = red-virt-analytics
├── uv.lock
├── ruff.toml
├── .github/workflows/ci.yml
├── .env.example
├── requirements.txt / requirements-dev.txt
│
└── src/
    ├── app.py
    ├── core/
    │   ├── config.py
    │   ├── constants.py
    │   ├── db_utils.py
    │   ├── exceptions.py
    │   ├── data_loader.py
    │   ├── inspector_base.py   # контекст SQL для инспекторов
    │   ├── sql_guard.py        # ad-hoc SELECT/WITH
    │   ├── sql_editor.py
    │   ├── report_text.py      # рамки текстовых отчётов
    │   ├── table_preview.py    # сырые таблицы (diagnostics)
    │   └── ui_utils.py
    │
    ├── hosts/                  # module, utils, diagnostics
    │   ├── host_inspector_sql.py
    │   └── host_inspector_sql.txt   # поле → таблица → колонка
    ├── vms/
    │   ├── vm_inspector_sql.py
    │   └── vm_inspector_sql.txt
    ├── snapshots/
    │   ├── snapshot_inspector_sql.py
    │   └── snapshot_inspector_sql.txt
    ├── clusters/
    │   ├── cluster_inspector_sql.py
    │   └── cluster_inspector_sql.txt
    ├── networks/
    │   ├── network_inspector_sql.py
    │   └── network_inspector_sql.txt
    ├── storage/
    │   ├── storage_inspector_sql.py
    │   └── storage_inspector_sql.txt
    ├── disks/
    │   ├── disks_inspector_sql.py
    │   └── disks_inspector_sql.txt
    ├── gluster/
    │   ├── gluster_inspector_sql.py
    │   └── gluster_inspector_sql.txt
    ├── tasks/                  # module, utils, diagnostics (без инспектора)
    ├── audit/
    ├── users/
    ├── system/
    ├── cert/                   # certificates.py
    └── atlas/
        ├── atlas_module.py
        ├── data_loader.py
        ├── renderer.py
        ├── compat.json
        ├── changelog.json
        └── data/*.json
```

## Руководство по модулям

### Хосты и ВМ
-   **Список:** Поиск по имени/FQDN, фильтрация по кластерам, выделение проблемных узлов.
-   **Инспектор:** Текстовый отчет со статусами, ресурсами, сетью и аудиторскими событиями.
-   **Происхождение полей:** `src/hosts/host_inspector_sql.txt`, `src/vms/vm_inspector_sql.txt`, `src/clusters/cluster_inspector_sql.txt`, `src/snapshots/snapshot_inspector_sql.txt`, `src/networks/network_inspector_sql.txt`, `src/storage/storage_inspector_sql.txt`, `src/disks/disks_inspector_sql.txt`, `src/gluster/gluster_inspector_sql.txt` (подпись в отчёте → колонка → таблица).
-   **Диагностика:** Прямой просмотр системных таблиц (`vds_static`, `vm_dynamic`) с защитой от переполнения памяти.

### Сети и Хранилища
-   Анализ логических сетей, vNIC профилей и состояния Storage Domains.
-   Проверка связей между хранилищами и дата-центрами, поиск несоответствий LUN.
-   **Происхождение полей:** `src/networks/network_inspector_sql.txt`, `src/storage/storage_inspector_sql.txt`, `src/disks/disks_inspector_sql.txt`, `src/gluster/gluster_inspector_sql.txt`.

### Задачи и Аудит
-   Мониторинг зависших задач (Jobs) и анализ журнала событий (Audit Log).
-   Выявление причин сбоев через корреляцию задач и логов.

## Безопасность и ограничения

1.  **Конфиденциальность:** Дампы БД содержат чувствительные данные. Храните их в защищенном месте.
2.  **Память:** При работе с `audit_log` или `event_history` используйте фильтр по дате. Выборка автоматически ограничена, но требует внимания при ручных запросах.
3.  **Локальный контур:** `docker-compose` публикует порт только на `127.0.0.1:8502`. С LAN и других интерфейсов хоста UI недоступен. Внутри контейнера Streamlit слушает `0.0.0.0:8501` — это нужно для проброса порта, не для внешнего доступа.
4.  **Режим чтения:** Каждое подключение к PostgreSQL открывается с `default_transaction_read_only=on` и `statement_timeout` (`STATEMENT_TIMEOUT_MS` в `.env`, по умолчанию 30000 мс). SQL-редактор принимает только SELECT/WITH (и EXPLAIN к ним), несколько стейтментов запрещены, выборка ограничена `MAX_ROW_LIMIT`. DML отклоняется и фильтром редактора, и самой БД.

Runtime проверен на pandas 3.x (пин в `pyproject.toml`).

Обновление зависимостей: правите прямые пакеты в `pyproject.toml`, затем `uv lock` и `uv export --frozen --no-dev --no-hashes -o requirements.txt` / `uv export --frozen --no-hashes -o requirements-dev.txt`. Docker по-прежнему ставит `requirements.txt`.

---
*Разработано для нужд технической поддержки виртуализации РЕД СОФТ.*

# Установка Docker в РЕД ОС 8

Инструкция предназначена для подготовки рабочей станции с РЕД ОС 8 к запуску RED Virt Analytics.

Официальная документация: [«Установка и настройка Docker» в Базе знаний РЕД ОС 8](https://redos.red-soft.ru/base/redos-8_0/8_0-administation/8_0-containers/8_0-docker-install/).

## 1. Проверьте версию операционной системы

```bash
cat /etc/redos-release
```

Инструкция рассчитана на РЕД ОС 8. Для РЕД ОС другой версии состав и версии пакетов могут отличаться.

## 2. Обновите сведения о пакетах

```bash
sudo dnf makecache
```

Рабочая станция должна иметь доступ к настроенным репозиториям РЕД ОС и к источнику базового образа, используемого приложением.

## 3. Установите Docker и Docker Compose

```bash
sudo dnf install -y docker-ce docker-ce-cli docker-compose
```

RED Virt Analytics использует команду `docker compose`, поэтому наличие только Docker Engine недостаточно.

## 4. Запустите Docker

```bash
sudo systemctl enable docker --now
```

Проверьте состояние службы:

```bash
systemctl status docker
```

Ожидаемое состояние:

```text
active (running)
```

Для выхода из просмотра статуса нажмите `q`.

## 5. Разрешите запуск Docker обычному пользователю

По умолчанию управление Docker может быть доступно только суперпользователю. Добавьте текущего пользователя в группу `docker`:

```bash
sudo usermod -aG docker "$USER"
```

После выполнения команды полностью выйдите из пользовательского сеанса и войдите снова. Открытия нового окна терминала недостаточно.

> Членство в группе `docker` предоставляет пользователю широкие полномочия на рабочей станции. Добавляйте в неё только доверенных пользователей.

## 6. Проверьте установку

После повторного входа выполните команды без `sudo`:

```bash
docker version
docker compose version
docker info
```

Все три команды должны завершиться без сообщений об отсутствии команды и без ошибки доступа к Docker socket.

Дополнительная проверка запуска контейнера:

```bash
docker run --rm hello-world
```

При первом выполнении Docker загрузит тестовый образ из реестра. Если доступ к внешнему реестру ограничен, эта проверка может завершиться ошибкой загрузки, даже если служба Docker установлена правильно.

## 7. Возможные проблемы

### `docker: command not found`

Пакеты Docker не установлены либо каталог с исполняемым файлом отсутствует в `PATH`.

Проверьте пакеты:

```bash
rpm -qa | grep -E '^docker'
```

### `docker: 'compose' is not a docker command`

Не установлен Docker Compose либо установлен несовместимый вариант.

Выполните:

```bash
sudo dnf install -y docker-compose
docker compose version
```

Для RED Virt Analytics требуется синтаксис с пробелом: `docker compose`, а не устаревшая отдельная команда `docker-compose`.

### `permission denied` при обращении к Docker socket

Проверьте группы текущего пользователя:

```bash
id
```

Если группы `docker` нет, повторите добавление пользователя и выполните полный выход из сеанса:

```bash
sudo usermod -aG docker "$USER"
```

### `Cannot connect to the Docker daemon`

Проверьте службу:

```bash
sudo systemctl restart docker
systemctl status docker
```

Посмотрите журнал службы:

```bash
sudo journalctl -u docker -n 100 --no-pager
```

### Не загружаются образы

Проверьте DNS, прокси-сервер, сетевой доступ и настройки реестров Docker. Рекомендации по настройке зеркал приведены в [официальной статье РЕД ОС](https://redos.red-soft.ru/base/redos-8_0/8_0-administation/8_0-containers/8_0-docker-install/).

Сборка образа RED Virt Analytics ставит пакет `curl` из репозиториев Debian. В Dockerfile указаны официальный источник (`deb.debian.org`) и зеркала (`ftp.ru.debian.org`, `mirror.yandex.ru`). Если недоступны и они, настройте корпоративный прокси Docker или соберите образ в сети с доступом к Debian.

## 8. Следующий шаг

После успешной проверки Docker вернитесь к [руководству администратора RED Virt Analytics](ADMIN_GUIDE.md) и продолжите установку приложения.
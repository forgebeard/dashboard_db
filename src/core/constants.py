# src/core/constants.py
"""
Глобальные справочники статусов и типов oVirt Engine.

Централизованное хранилище маппингов числовых кодов БД в читаемые 
человеко-понятные значения для UI дашборда. Включает прямые и 
обратные словари для удобного поиска и фильтрации.
"""

from typing import Dict, Union

# --- СТАТУСЫ ВИРТУАЛЬНЫХ МАШИН (VmStatus.java) ---
VM_STATUS_MAP: Dict[int, str] = {
    -1: 'Unassigned',        # Статус не назначен
    0: 'Down',               # ВМ выключена
    1: 'Up',                 # ВМ запущена и работает
    2: 'PoweringUp',         # Процесс запуска ВМ
    4: 'Paused',             # ВМ на паузе
    5: 'MigratingFrom',      # Исходящая миграция
    6: 'MigratingTo',        # Входящая миграция
    7: 'Unknown',            # Неизвестный статус
    8: 'NotResponding',      # Нет ответа от агента/хоста
    9: 'WaitForLaunch',      # Ожидание запуска
    10: 'RebootInProgress',  # Перезагрузка
    11: 'SavingState',       # Сохранение состояния
    12: 'RestoringState',    # Восстановление состояния
    13: 'Suspended',         # Приостановлена
    14: 'ImageIllegal',      # Проблемы с образом диска
    15: 'ImageLocked',       # Образ заблокирован операцией
    16: 'PoweringDown'       # Процесс выключения
}

# Обратный маппинг: Имя статуса -> Код
VM_NAME_TO_STATUS: Dict[str, int] = {v: k for k, v in VM_STATUS_MAP.items()}

# --- СТАТУСЫ ХОСТОВ (VDSStatus.java) ---
HOST_STATUS_MAP: Dict[int, str] = {
    0: 'Unassigned',               # Статус не назначен
    1: 'Down',                     # Хост выключен/недоступен
    2: 'Maintenance',              # Режим обслуживания
    3: 'Up',                       # Хост активен
    4: 'NonResponsive',            # Хост не отвечает
    5: 'Error',                    # Ошибка на хосте
    6: 'Installing',               # Установка ОС/агента
    7: 'InstallFailed',            # Ошибка установки
    8: 'Reboot',                   # Перезагрузка
    9: 'PreparingForMaintenance',  # Подготовка к обслуживанию
    10: 'NonOperational',          # Неоперабельное состояние
    11: 'PendingApproval',         # Ожидает одобрения
    12: 'Initializing',            # Инициализация
    13: 'Connecting',              # Подключение к движку
    14: 'InstallingOS',            # Установка ОС
    15: 'Kdumping'                 # Снятие дампа памяти (kdump)
}

# Обратный маппинг: Имя статуса -> Код
HOST_NAME_TO_STATUS: Dict[str, int] = {v: k for k, v in HOST_STATUS_MAP.items()}

# --- ТИПЫ ДОМЕНОВ ХРАНЕНИЯ (StorageDomainType) ---
STORAGE_DOMAIN_TYPE_MAP: Dict[int, str] = {
    0: "Data",      # Домен данных
    1: "ISO",       # ISO-образы
    2: "Export",    # Экспорт/Импорт
    3: "Image"      # Передача образов (Image Transfer)
}

# --- ФИЗИЧЕСКИЕ ТИПЫ ПОДКЛЮЧЕНИЯ (StorageType) ---
STORAGE_TYPE_MAP: Dict[int, str] = {
    1: "NFS",
    2: "iSCSI",
    3: "Local",
    4: "FCP",       # Fibre Channel Protocol
    5: "NAS",
    6: "POSIXFS",
    7: "GlusterFS",
    8: "OpenStack Glance"
}

# --- СТАТУСЫ ОБРАЗОВ ДИСКОВ (ImageStatus) ---
IMAGE_STATUS_MAP: Dict[int, str] = {
    1: "OK",
    2: "LOCKED",     # Заблокирован операцией (snapshot, migrate)
    3: "ILLEGAL",    # Поврежден или несогласован
    4: "MERGING"     # Идет слияние снапшотов
}

# --- СТАТУСЫ ОБЩИХ ДОМЕНОВ (SharedStatus) ---
SHARED_STATUS_MAP: Dict[int, str] = {
    0: "Unknown",
    1: "Active",     # Активен и доступен
    2: "Maintenance",# В обслуживании
    3: "Problem"     # Проблемы с доступностью
}
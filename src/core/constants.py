# src/core/constants.py
"""
Глобальные справочники статусов и типов oVirt Engine.

Централизованное хранилище маппингов числовых кодов БД в читаемые 
человеко-понятные значения для UI дашборда. Включает прямые и 
обратные словари для удобного поиска и фильтрации.
"""

from collections.abc import Iterable
from typing import Dict, Literal

StatusTone = Literal["success", "warning", "critical", "neutral"]

HOST_STATUS_UP = 3
HOST_MAINTENANCE_CODES = frozenset({2, 8, 9})  # Maintenance, Reboot, PreparingForMaintenance
HOST_CRITICAL_CODES = frozenset({4, 5, 7, 10, 15})  # NonResponsive, Error, InstallFailed, NonOperational, Kdumping
HOST_NEUTRAL_CODES = frozenset({0, 1})  # Unassigned, Down

VM_STATUS_UP = 1
VM_STATUS_DOWN = 0
VM_STATUS_PAUSED = 4
VM_CRITICAL_CODES = frozenset({7, 8, 14, 15})  # Unknown, NotResponding, ImageIllegal, ImageLocked

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


def _as_int_code(code: object) -> int | None:
    if code is None:
        return None
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def host_is_healthy(status_code: object) -> bool:
    return _as_int_code(status_code) == HOST_STATUS_UP


def host_is_maintenance(status_code: object) -> bool:
    code = _as_int_code(status_code)
    return code in HOST_MAINTENANCE_CODES if code is not None else False


def host_is_problem(status_code: object) -> bool:
    """Проблема: не Up и не регламентное обслуживание."""
    if host_is_healthy(status_code) or host_is_maintenance(status_code):
        return False
    return _as_int_code(status_code) is not None


def host_status_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == HOST_STATUS_UP:
        return "success"
    if code in HOST_MAINTENANCE_CODES:
        return "warning"
    if code in HOST_CRITICAL_CODES:
        return "critical"
    if code in HOST_NEUTRAL_CODES:
        return "neutral"
    return "warning"


def vm_is_problem(status_code: object, has_bad_images: bool = False) -> bool:
    return _as_int_code(status_code) != VM_STATUS_UP or bool(has_bad_images)


def vm_status_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == VM_STATUS_UP:
        return "success"
    if code == VM_STATUS_DOWN:
        return "neutral"
    if code in VM_CRITICAL_CODES:
        return "critical"
    return "warning"


def host_health_counts(status_codes: Iterable[object]) -> dict[str, int]:
    codes = list(status_codes)
    return {
        "total": len(codes),
        "up": sum(1 for c in codes if host_is_healthy(c)),
        "maintenance": sum(1 for c in codes if host_is_maintenance(c)),
        "problems": sum(1 for c in codes if host_is_problem(c)),
    }


def vm_health_counts(
    status_codes: Iterable[object],
    bad_images: Iterable[object] | None = None,
) -> dict[str, int]:
    codes = list(status_codes)
    flags = list(bad_images) if bad_images is not None else [False] * len(codes)
    if len(flags) != len(codes):
        flags = [False] * len(codes)
    return {
        "total": len(codes),
        "up": sum(1 for c in codes if _as_int_code(c) == VM_STATUS_UP),
        "down": sum(1 for c in codes if _as_int_code(c) == VM_STATUS_DOWN),
        "paused": sum(1 for c in codes if _as_int_code(c) == VM_STATUS_PAUSED),
        "problems": sum(
            1 for c, bad in zip(codes, flags) if vm_is_problem(c, bool(bad))
        ),
    }
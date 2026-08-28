# src/core/constants.py
"""
Глобальные справочники статусов и типов oVirt Engine.

Централизованное хранилище маппингов числовых кодов БД в читаемые 
человеко-понятные значения для UI дашборда. Включает прямые и 
обратные словари для удобного поиска и фильтрации.
"""

from collections.abc import Iterable
from typing import Dict, Literal

from core.action_type_map import ACTION_TYPE_MAP

StatusTone = Literal["success", "warning", "critical", "neutral"]

HOST_STATUS_UP = 3
HOST_MAINTENANCE_CODES = frozenset({2, 8, 9})  # Maintenance, Reboot, PreparingForMaintenance
HOST_CRITICAL_CODES = frozenset({4, 5, 7, 10, 15})  # NonResponsive, Error, InstallFailed, NonOperational, Kdumping
HOST_NEUTRAL_CODES = frozenset({0, 1})  # Unassigned, Down

# Сводный статус кластера (нет кода Engine): по составу хостов.
CLUSTER_STATUS_OK = 0
CLUSTER_STATUS_PROBLEMS = 1
CLUSTER_STATUS_MAP: Dict[int, str] = {
    CLUSTER_STATUS_OK: "Ok",
    CLUSTER_STATUS_PROBLEMS: "Проблемы",
}

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

# --- АРХИТЕКТУРА (ArchitectureType) ---
# Коды как в Engine PostgreSQL (cluster.architecture, vm_static.cpu_architecture).
# Источник:
#   oVirt Engine ArchitectureType.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/compat/ArchitectureType.java
# Дамп 4.6: Cascadelake → architecture=1 (x86_64). Не путать с 0=x86_64 / 1=aarch64.
ARCHITECTURE_MAP: Dict[int, str] = {
    0: "undefined",
    1: "x86_64",
    2: "ppc64",
    3: "ppc",
    4: "s390x",
    5: "aarch64",
}

# --- BIOS (BiosType) ---
# Коды как в Engine (cluster.bios_type, vm_static.bios_type).
# Источник:
#   oVirt Engine BiosType.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/BiosType.java
BIOS_TYPE_MAP: Dict[int, str] = {
    0: "Cluster default",
    1: "i440FX SeaBIOS",
    2: "Q35 SeaBIOS",
    3: "Q35 OVMF",
    4: "Q35 SecureBoot",
}

# --- МИГРАЦИЯ ПРИ ОШИБКЕ ХОСТА (MigrateOnError) ---
# cluster.migrate_on_error
MIGRATE_ON_ERROR_MAP: Dict[int, str] = {
    0: "DoNothing",
    1: "Migrate",
    2: "Shutdown",
}

# --- ЖУРНАЛ (AuditLogSeverity) ---
# Коды как в Engine PostgreSQL (audit_log.severity).
# Источник:
#   oVirt Engine AuditLogSeverity.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/AuditLogSeverity.java
# Дамп: 0 Normal, 1 Warning, 2 Error, 3 Alert. Прочие коды не угадывать.
AUDIT_SEVERITY_NORMAL = 0
AUDIT_SEVERITY_WARNING = 1
AUDIT_SEVERITY_ERROR = 2
AUDIT_SEVERITY_ALERT = 3
AUDIT_SEVERITY_MAP: Dict[int, str] = {
    AUDIT_SEVERITY_NORMAL: "Normal",
    AUDIT_SEVERITY_WARNING: "Warning",
    AUDIT_SEVERITY_ERROR: "Error",
    AUDIT_SEVERITY_ALERT: "Alert",
}

# --- ASYNC-ЗАДАЧИ (AsyncTaskStatusEnum) ---
# Коды как в Engine (async_tasks.status), явные значения из Java, не ordinal().
# Источник:
#   oVirt Engine AsyncTaskStatusEnum.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/AsyncTaskStatusEnum.java
ASYNC_TASK_STATUS_MAP: Dict[int, str] = {
    0: "unknown",
    1: "init",
    2: "running",
    3: "finished",
    4: "aborting",
    5: "cleaning",
}

# --- РЕЗУЛЬТАТ ASYNC-ЗАДАЧИ (AsyncTaskResultEnum) ---
# Коды как в Engine (async_tasks.result), ordinal enum.
# Источник:
#   oVirt Engine AsyncTaskResultEnum.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/AsyncTaskResultEnum.java
ASYNC_TASK_RESULT_MAP: Dict[int, str] = {
    0: "success",
    1: "failure",
    2: "cleanSuccess",
    3: "cleanFailure",
    4: "unknown",
}

# --- ТИПЫ ДОМЕНОВ ХРАНЕНИЯ (StorageDomainType) ---
# Коды как в Engine PostgreSQL (storage_domain_static.storage_domain_type).
# Источники:
#   oVirt Engine StorageDomainType.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/StorageDomainType.java
#   VDSM lib/vdsm/storage/sd.py (классы DATA/ISO/BACKUP — параллельный enum ролей)
STORAGE_DOMAIN_TYPE_MAP: Dict[int, str] = {
    0: "Master",
    1: "Data",
    2: "ISO",
    3: "ImportExport",
    4: "Image",
    5: "Volume",
    6: "Unknown",
    7: "ManagedBlockStorage",
}

# --- ФИЗИЧЕСКИЕ ТИПЫ ПОДКЛЮЧЕНИЯ (StorageType) ---
# Коды как в Engine PostgreSQL (storage_domain_static.storage_type,
# storage_server_connections.storage_type).
# Источники:
#   oVirt Engine StorageType.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/storage/StorageType.java
#   VDSM lib/vdsm/storage/sd.py (NFS_DOMAIN=1, FCP_DOMAIN=2, ISCSI_DOMAIN=3, ...)
# Код 5 в актуальном Engine пропущен; в VDSM 5 = CIFS.
STORAGE_TYPE_MAP: Dict[int, str] = {
    0: "UNKNOWN",
    1: "NFS",
    2: "FCP",
    3: "iSCSI",
    4: "LocalFS",
    5: "CIFS",
    6: "POSIXFS",
    7: "GlusterFS",
    8: "Glance",
    9: "Cinder",
    10: "ManagedBlockStorage",
}

# --- СТАТУСЫ ОБРАЗОВ ДИСКОВ (ImageStatus) ---
IMAGE_STATUS_OK = 1
IMAGE_STATUS_LOCKED = 2
IMAGE_STATUS_ILLEGAL = 3
IMAGE_STATUS_MERGING = 4
IMAGE_STATUS_MAP: Dict[int, str] = {
    IMAGE_STATUS_OK: "OK",
    IMAGE_STATUS_LOCKED: "LOCKED",     # Заблокирован операцией (snapshot, migrate)
    IMAGE_STATUS_ILLEGAL: "ILLEGAL",    # Поврежден или несогласован
    IMAGE_STATUS_MERGING: "MERGING",    # Идет слияние снапшотов
}
# Хуже → лучше: ILLEGAL, LOCKED, MERGING.
IMAGE_LAYER_ISSUE_ORDER: tuple[int, ...] = (
    IMAGE_STATUS_ILLEGAL,
    IMAGE_STATUS_LOCKED,
    IMAGE_STATUS_MERGING,
)

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


def vm_is_problem(status_code: object) -> bool:
    """Остальное: не Up и не Down."""
    if _as_int_code(status_code) in (VM_STATUS_UP, VM_STATUS_DOWN):
        return False
    return _as_int_code(status_code) is not None


def vm_status_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == VM_STATUS_UP:
        return "success"
    if code == VM_STATUS_DOWN:
        return "neutral"
    if code in VM_CRITICAL_CODES:
        return "critical"
    return "warning"


def vm_layer_tone(status_code: object) -> StatusTone | None:
    code = _as_int_code(status_code)
    if code == IMAGE_STATUS_ILLEGAL:
        return "critical"
    if code in (IMAGE_STATUS_LOCKED, IMAGE_STATUS_MERGING):
        return "warning"
    return None


def _as_count(value: object) -> int:
    code = _as_int_code(value)
    return code if code is not None and code > 0 else 0


def cluster_status_from_hosts(
    host_problems: object, host_maintenance: object = None
) -> int:
    """Ok, если нет problem-хостов (maintenance хостов не считается проблемой)."""
    if _as_count(host_problems) > 0:
        return CLUSTER_STATUS_PROBLEMS
    return CLUSTER_STATUS_OK


def cluster_status_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == CLUSTER_STATUS_OK:
        return "success"
    if code == CLUSTER_STATUS_PROBLEMS:
        return "critical"
    return "neutral"


def mapped_code_label(code: object, mapping: Dict[int, str]) -> str:
    parsed = _as_int_code(code)
    if parsed is None:
        return "—"
    return mapping.get(parsed, f"Code {parsed}")


def audit_severity_label(status_code: object) -> str:
    return mapped_code_label(status_code, AUDIT_SEVERITY_MAP)


def audit_severity_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == AUDIT_SEVERITY_NORMAL:
        return "neutral"
    if code == AUDIT_SEVERITY_WARNING:
        return "warning"
    if code in (AUDIT_SEVERITY_ERROR, AUDIT_SEVERITY_ALERT):
        return "critical"
    return "neutral"


def async_task_status_label(status_code: object) -> str:
    return mapped_code_label(status_code, ASYNC_TASK_STATUS_MAP)


def async_task_result_label(status_code: object) -> str:
    return mapped_code_label(status_code, ASYNC_TASK_RESULT_MAP)


def action_type_label(status_code: object) -> str:
    return mapped_code_label(status_code, ACTION_TYPE_MAP)


def cluster_health_counts(status_codes: Iterable[object]) -> dict[str, int]:
    codes = list(status_codes)
    return {
        "total": len(codes),
        "ok": sum(1 for c in codes if _as_int_code(c) == CLUSTER_STATUS_OK),
        "problems": sum(
            1 for c in codes if _as_int_code(c) == CLUSTER_STATUS_PROBLEMS
        ),
    }


def host_health_counts(status_codes: Iterable[object]) -> dict[str, int]:
    codes = list(status_codes)
    return {
        "total": len(codes),
        "up": sum(1 for c in codes if host_is_healthy(c)),
        "maintenance": sum(1 for c in codes if host_is_maintenance(c)),
        "problems": sum(1 for c in codes if host_is_problem(c)),
    }


def vm_health_counts(status_codes: Iterable[object]) -> dict[str, int]:
    codes = list(status_codes)
    return {
        "total": len(codes),
        "up": sum(1 for c in codes if _as_int_code(c) == VM_STATUS_UP),
        "down": sum(1 for c in codes if _as_int_code(c) == VM_STATUS_DOWN),
        "problems": sum(1 for c in codes if vm_is_problem(c)),
    }
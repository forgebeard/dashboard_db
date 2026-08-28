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

# --- ТИП ОБЪЕКТА ПРАВ (VdcObjectType) ---
# Коды как в Engine (permissions.object_type_id), явные value(), не ordinal().
# Источник:
#   oVirt Engine VdcObjectType.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/VdcObjectType.java
# Дамп: DiskOperator на object_type_id=19 (Disk).
VDC_OBJECT_TYPE_MAP: Dict[int, str] = {
    1: "каталог",
    2: "система",
    3: "хранилище",
    4: "дата-центр",
    5: "ВМ",
    6: "шаблон",
    7: "пул ВМ",
    8: "хост",
    9: "кластер",
    10: "закладка",
    11: "категория",
    12: "тег",
    13: "пользователь",
    14: "право",
    15: "роль",
    16: "уведомление",
    17: "квота",
    18: "том Gluster",
    19: "диск",
    20: "сеть",
    21: "профиль vNIC",
    22: "пул MAC",
}

# --- ASYNC-ЗАДАЧИ (AsyncTaskStatusEnum) ---
# Коды как в Engine (async_tasks.status), явные значения из Java, не ordinal().
# Источник:
#   oVirt Engine AsyncTaskStatusEnum.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/AsyncTaskStatusEnum.java
ASYNC_TASK_STATUS_UNKNOWN = 0
ASYNC_TASK_STATUS_INIT = 1
ASYNC_TASK_STATUS_RUNNING = 2
ASYNC_TASK_STATUS_FINISHED = 3
ASYNC_TASK_STATUS_ABORTING = 4
ASYNC_TASK_STATUS_CLEANING = 5
ASYNC_TASK_STATUS_MAP: Dict[int, str] = {
    ASYNC_TASK_STATUS_UNKNOWN: "unknown",
    ASYNC_TASK_STATUS_INIT: "init",
    ASYNC_TASK_STATUS_RUNNING: "running",
    ASYNC_TASK_STATUS_FINISHED: "finished",
    ASYNC_TASK_STATUS_ABORTING: "aborting",
    ASYNC_TASK_STATUS_CLEANING: "cleaning",
}
ASYNC_TASK_RUNNING_CODES = frozenset(
    {
        ASYNC_TASK_STATUS_INIT,
        ASYNC_TASK_STATUS_RUNNING,
        ASYNC_TASK_STATUS_ABORTING,
        ASYNC_TASK_STATUS_CLEANING,
    }
)

# --- РЕЗУЛЬТАТ ASYNC-ЗАДАЧИ (AsyncTaskResultEnum) ---
# Коды как в Engine (async_tasks.result), ordinal enum.
# Источник:
#   oVirt Engine AsyncTaskResultEnum.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/AsyncTaskResultEnum.java
ASYNC_TASK_RESULT_SUCCESS = 0
ASYNC_TASK_RESULT_FAILURE = 1
ASYNC_TASK_RESULT_CLEAN_SUCCESS = 2
ASYNC_TASK_RESULT_CLEAN_FAILURE = 3
ASYNC_TASK_RESULT_UNKNOWN = 4
ASYNC_TASK_RESULT_MAP: Dict[int, str] = {
    ASYNC_TASK_RESULT_SUCCESS: "success",
    ASYNC_TASK_RESULT_FAILURE: "failure",
    ASYNC_TASK_RESULT_CLEAN_SUCCESS: "cleanSuccess",
    ASYNC_TASK_RESULT_CLEAN_FAILURE: "cleanFailure",
    ASYNC_TASK_RESULT_UNKNOWN: "unknown",
}
ASYNC_TASK_RESULT_ERROR_CODES = frozenset(
    {ASYNC_TASK_RESULT_FAILURE, ASYNC_TASK_RESULT_CLEAN_FAILURE}
)
ASYNC_TASK_BUCKET_FINISHED = 0
ASYNC_TASK_BUCKET_RUNNING = 1
ASYNC_TASK_BUCKET_ERRORS = 2

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

# --- СТАТУСЫ ОБЩИХ ДОМЕНОВ (StorageDomainSharedStatus) ---
# Коды как в Engine PostgreSQL (storage_domain_shared_status.status), ordinal enum.
# Источник:
#   oVirt Engine StorageDomainSharedStatus.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/StorageDomainSharedStatus.java
STORAGE_SHARED_UNATTACHED = 0
STORAGE_SHARED_ACTIVE = 1
STORAGE_SHARED_INACTIVE = 2
STORAGE_SHARED_MIXED = 3
SHARED_STATUS_MAP: Dict[int, str] = {
    STORAGE_SHARED_UNATTACHED: "Unattached",
    STORAGE_SHARED_ACTIVE: "Active",
    STORAGE_SHARED_INACTIVE: "Inactive",
    STORAGE_SHARED_MIXED: "Mixed",
}

# --- СТАТУС ПРИВЯЗКИ ДОМЕНА К ДЦ (StorageDomainStatus) ---
# Коды как в Engine (storage_pool_iso_map.status).
# Источник:
#   oVirt Engine StorageDomainStatus.java
#     https://github.com/oVirt/ovirt-engine/blob/master/backend/manager/modules/common/src/main/java/org/ovirt/engine/core/common/businessentities/StorageDomainStatus.java
STORAGE_DOMAIN_STATUS_ACTIVE = 3
STORAGE_DOMAIN_STATUS_MAP: Dict[int, str] = {
    0: "Unknown",
    1: "Uninitialized",
    2: "Unattached",
    3: "Active",
    4: "Inactive",
    5: "Locked",
    6: "Maintenance",
    7: "PreparingForMaintenance",
    8: "Detaching",
    9: "Activating",
}

# storage_pool.status
STORAGE_POOL_STATUS_MAP: Dict[int, str] = {
    0: "Uninitialized",
    1: "Up",
    2: "Maintenance",
    3: "NotOperational",
    4: "Problematic",
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


def image_is_ok(status_code: object) -> bool:
    return _as_int_code(status_code) == IMAGE_STATUS_OK


def image_is_problem(status_code: object) -> bool:
    """Остальное: известный imagestatus, но не OK."""
    if image_is_ok(status_code):
        return False
    return _as_int_code(status_code) is not None


def image_status_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == IMAGE_STATUS_OK:
        return "success"
    if code == IMAGE_STATUS_ILLEGAL:
        return "critical"
    if code in (IMAGE_STATUS_LOCKED, IMAGE_STATUS_MERGING):
        return "warning"
    return "warning"


def image_health_counts(status_codes: Iterable[object]) -> dict[str, int]:
    codes = list(status_codes)
    return {
        "total": len(codes),
        "ok": sum(1 for c in codes if image_is_ok(c)),
        "problems": sum(1 for c in codes if image_is_problem(c)),
    }


def storage_is_problem(status_code: object) -> bool:
    """Остальное: не Active (включая Unattached, Inactive, Mixed)."""
    code = _as_int_code(status_code)
    if code is None:
        return False
    return code != STORAGE_SHARED_ACTIVE


def storage_status_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == STORAGE_SHARED_ACTIVE:
        return "success"
    if code == STORAGE_SHARED_UNATTACHED:
        return "neutral"
    if code == STORAGE_SHARED_MIXED:
        return "warning"
    if code == STORAGE_SHARED_INACTIVE:
        return "critical"
    return "neutral"


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


def vdc_object_type_label(status_code: object) -> str:
    parsed = _as_int_code(status_code)
    if parsed is None:
        return "—"
    return VDC_OBJECT_TYPE_MAP.get(parsed, f"тип {parsed}")


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


def storage_health_counts(status_codes: Iterable[object]) -> dict[str, int]:
    codes = list(status_codes)
    return {
        "total": len(codes),
        "active": sum(
            1 for c in codes if _as_int_code(c) == STORAGE_SHARED_ACTIVE
        ),
        "problems": sum(1 for c in codes if storage_is_problem(c)),
    }


def audit_is_warning(status_code: object) -> bool:
    return _as_int_code(status_code) == AUDIT_SEVERITY_WARNING


def audit_is_error(status_code: object) -> bool:
    return _as_int_code(status_code) in (AUDIT_SEVERITY_ERROR, AUDIT_SEVERITY_ALERT)


def audit_health_counts(status_codes: Iterable[object]) -> dict[str, int]:
    codes = list(status_codes)
    return {
        "total": len(codes),
        "warning": sum(1 for c in codes if audit_is_warning(c)),
        "errors": sum(1 for c in codes if audit_is_error(c)),
    }


def async_task_is_error(status_code: object, result_code: object) -> bool:
    if _as_int_code(result_code) in ASYNC_TASK_RESULT_ERROR_CODES:
        return True
    return _as_int_code(status_code) == ASYNC_TASK_STATUS_UNKNOWN


def async_task_is_running(status_code: object, result_code: object) -> bool:
    if async_task_is_error(status_code, result_code):
        return False
    return _as_int_code(status_code) in ASYNC_TASK_RUNNING_CODES


def async_task_is_finished(status_code: object, result_code: object) -> bool:
    if async_task_is_error(status_code, result_code):
        return False
    return _as_int_code(status_code) == ASYNC_TASK_STATUS_FINISHED


def async_task_bucket_code(status_code: object, result_code: object) -> int:
    if async_task_is_error(status_code, result_code):
        return ASYNC_TASK_BUCKET_ERRORS
    if async_task_is_running(status_code, result_code):
        return ASYNC_TASK_BUCKET_RUNNING
    return ASYNC_TASK_BUCKET_FINISHED


def async_task_bucket_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code == ASYNC_TASK_BUCKET_ERRORS:
        return "critical"
    if code == ASYNC_TASK_BUCKET_RUNNING:
        return "warning"
    if code == ASYNC_TASK_BUCKET_FINISHED:
        return "success"
    return "neutral"


def async_task_result_tone(status_code: object) -> StatusTone:
    code = _as_int_code(status_code)
    if code in ASYNC_TASK_RESULT_ERROR_CODES:
        return "critical"
    if code in (ASYNC_TASK_RESULT_SUCCESS, ASYNC_TASK_RESULT_CLEAN_SUCCESS):
        return "success"
    return "warning"


def async_task_health_counts(
    pairs: Iterable[tuple[object, object]],
) -> dict[str, int]:
    items = list(pairs)
    return {
        "total": len(items),
        "running": sum(1 for status, result in items if async_task_is_running(status, result)),
        "finished": sum(1 for status, result in items if async_task_is_finished(status, result)),
        "errors": sum(1 for status, result in items if async_task_is_error(status, result)),
    }
#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly DIST_DIR="${SCRIPT_DIR}/dist"

usage() {
    printf 'Использование: %s [--force] VERSION\n' "$(basename -- "$0")"
    printf 'Пример:       %s 0.1.0\n' "$(basename -- "$0")"
    printf '              %s --force 0.1.0\n' "$(basename -- "$0")"
}

fail() {
    printf 'Ошибка: %s\n' "$1" >&2
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

FORCE=0
VERSION=""

for arg in "$@"; do
    case "$arg" in
        --force|-f)
            FORCE=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            fail "Неизвестный параметр '${arg}'."
            ;;
        *)
            if [[ -n "$VERSION" ]]; then
                usage
                fail "Лишний аргумент '${arg}'."
            fi
            VERSION="$arg"
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    usage
    exit 2
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z][0-9A-Za-z.-]*)?$ ]]; then
    fail "Некорректная версия '${VERSION}'. Ожидается формат 0.1.0 или 0.1.0-rc1."
fi

command_exists zip || fail "Не найдена команда zip. Установите пакет zip."
command_exists sha256sum || fail "Не найдена команда sha256sum."

readonly REQUIRED_PATHS=(
    "src"
    ".streamlit"
    "logs/.gitkeep"
    "Dockerfile"
    "docker-compose.yml"
    "start.sh"
    "start.bat"
    "requirements.txt"
    ".env.example"
    "README.md"
    "docs"
    "LICENSE"
    "VERSION"
)

for required_path in "${REQUIRED_PATHS[@]}"; do
    if [[ ! -e "${SCRIPT_DIR}/${required_path}" ]]; then
        fail "Отсутствует обязательный файл или каталог: ${required_path}"
    fi
done

if [[ ! -f "${SCRIPT_DIR}/src/app.py" ]]; then
    fail "Не найдена точка входа src/app.py."
fi

readonly RELEASE_NAME="red-virt-analytics-${VERSION}"
readonly ARCHIVE_PATH="${DIST_DIR}/${RELEASE_NAME}.zip"
readonly CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"

mkdir -p -- "$DIST_DIR"

if [[ -e "$ARCHIVE_PATH" || -e "$CHECKSUM_PATH" ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
        rm -f -- "$ARCHIVE_PATH" "$CHECKSUM_PATH"
    else
        fail "Релиз ${VERSION} уже существует в каталоге dist. Удалите его, укажите другую версию или используйте --force."
    fi
fi

readonly TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/red-virt-analytics-release.XXXXXX")"
readonly STAGE_DIR="${TEMP_DIR}/${RELEASE_NAME}"

cleanup() {
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
        rm -rf -- "$TEMP_DIR"
    fi
}

trap cleanup EXIT INT TERM

mkdir -p -- "$STAGE_DIR"

for required_path in "${REQUIRED_PATHS[@]}"; do
    target_parent="${STAGE_DIR}/$(dirname -- "$required_path")"
    mkdir -p -- "$target_parent"
    cp -a -- "${SCRIPT_DIR}/${required_path}" "$target_parent/"
done

printf '%s\n' "$VERSION" > "${STAGE_DIR}/VERSION"
chmod +x "${STAGE_DIR}/start.sh"

rm -f -- "${STAGE_DIR}/.streamlit/secrets.toml"

# Кэш Python может находиться внутри src после локального запуска тестов.
if [[ -d "${STAGE_DIR}/src" ]]; then
    find "${STAGE_DIR}/src" -depth -type d -name '__pycache__' -exec rm -rf -- {} +
    find "${STAGE_DIR}/src" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
fi

for forbidden_dir in tests .git .github .venv .pytest_cache .ruff_cache; do
    if find "$STAGE_DIR" -type d -name "$forbidden_dir" -print -quit | grep -q .; then
        fail "В поставку попал запрещённый каталог: ${forbidden_dir}"
    fi
done

forbidden_file="$({
    find "$STAGE_DIR" -type f \
        \( -name '.env' \
        -o -name 'secrets.toml' \
        -o -name '*.dump' \
        -o -name '*.sql' \
        -o -name '*.sql.gz' \
        -o -name '*.log' \
        -o -name '.coverage' \
        -o -name 'requirements-dev.txt' \
        -o -name 'pytest.ini' \
        -o -name 'ruff.toml' \
        -o -name 'uv.lock' \
        -o -name 'pyproject.toml' \) \
        -print -quit
} || true)"

if [[ -n "$forbidden_file" ]]; then
    fail "В поставку попал запрещённый файл: ${forbidden_file#${STAGE_DIR}/}"
fi

for required_path in "${REQUIRED_PATHS[@]}" VERSION; do
    if [[ ! -e "${STAGE_DIR}/${required_path}" ]]; then
        fail "После подготовки поставки отсутствует: ${required_path}"
    fi
done

(
    cd -- "$TEMP_DIR"
    zip -qr "$ARCHIVE_PATH" "$RELEASE_NAME"
)

if [[ ! -s "$ARCHIVE_PATH" ]]; then
    fail "Архив не создан или имеет нулевой размер."
fi

(
    cd -- "$DIST_DIR"
    sha256sum "$(basename -- "$ARCHIVE_PATH")" > "$(basename -- "$CHECKSUM_PATH")"
)

printf '\nПользовательская поставка сформирована успешно.\n'
printf 'Архив:           %s\n' "$ARCHIVE_PATH"
printf 'Контрольная сумма: %s\n' "$CHECKSUM_PATH"
printf 'Версия:          %s\n' "$VERSION"

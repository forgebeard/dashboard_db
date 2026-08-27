#!/bin/bash
set -e

ENV_FILE=".env"

# Флаг перенастройки
if [ "$1" = "--reconfigure" ] || [ "$1" = "-r" ]; then
    rm -f "$ENV_FILE"
    echo "🔄 .env удалён. Перенастройка..."
    echo ""
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "📝 Настройка подключения к БД."
    echo ""

    read -rp "DB_HOST [host.docker.internal]: " DB_HOST
    DB_HOST=${DB_HOST:-host.docker.internal}

    read -rp "DB_PORT [5432]: " DB_PORT
    DB_PORT=${DB_PORT:-5432}

    read -rp "DB_NAME [engine]: " DB_NAME
    DB_NAME=${DB_NAME:-engine}

    read -rp "DB_USER [postgres]: " DB_USER
    DB_USER=${DB_USER:-postgres}

    read -rsp "DB_PASSWORD: " DB_PASSWORD
    echo ""

    if [ -z "$DB_PASSWORD" ]; then
        echo "❌ Пароль не может быть пустым."
        exit 1
    fi

    cat > "$ENV_FILE" <<EOF
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
EOF

    echo "✅ .env создан."
    echo ""
fi

docker compose up -d --build
echo ""
echo "✅ RED Virt Analytics запущен: http://localhost:8502"
echo "   Перенастроить: ./start.sh -r"
echo "   Остановить:    docker compose down"
echo "   Логи:          docker compose logs -f"
@echo off
chcp 65001 >nul

if "%1"=="-r" (
    del /q .env 2>nul
    echo Перенастройка...
    echo.
)

if not exist .env (
    echo Настройка подключения к БД.
    echo.
    set /p DB_HOST=DB_HOST [host.docker.internal]: 
    if "%DB_HOST%"=="" set DB_HOST=host.docker.internal

    set /p DB_PORT=DB_PORT [5432]: 
    if "%DB_PORT%"=="" set DB_PORT=5432

    set /p DB_NAME=DB_NAME [engine]: 
    if "%DB_NAME%"=="" set DB_NAME=engine

    set /p DB_USER=DB_USER [postgres]: 
    if "%DB_USER%"=="" set DB_USER=postgres

    set /p DB_PASSWORD=DB_PASSWORD: 
    if "%DB_PASSWORD%"=="" (
        echo Пароль не может быть пустым.
        exit /b 1
    )

    echo DB_HOST=%DB_HOST%> .env
    echo DB_PORT=%DB_PORT%>> .env
    echo DB_NAME=%DB_NAME%>> .env
    echo DB_USER=%DB_USER%>> .env
    echo DB_PASSWORD=%DB_PASSWORD%>> .env

    echo.
    echo .env создан.
    echo.
)

docker compose up -d --build
echo.
echo RED Virt Analytics запущен: http://localhost:8502
echo   Перенастроить: start.bat -r
echo   Остановить:    docker compose down
echo   Логи:          docker compose logs -f
"""Общие фикстуры: переменные из корневого .env для интеграционных тестов."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

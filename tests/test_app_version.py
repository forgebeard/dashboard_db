from pathlib import Path

from core.config import app_version


def test_app_version_reads_file(tmp_path: Path) -> None:
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.2.3\n", encoding="utf-8")
    assert app_version(version_file) == "1.2.3"


def test_app_version_missing_file(tmp_path: Path) -> None:
    assert app_version(tmp_path / "VERSION") == "dev"


def test_app_version_empty_file(tmp_path: Path) -> None:
    version_file = tmp_path / "VERSION"
    version_file.write_text("  \n", encoding="utf-8")
    assert app_version(version_file) == "dev"

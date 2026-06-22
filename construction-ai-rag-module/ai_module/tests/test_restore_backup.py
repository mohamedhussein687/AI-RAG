from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from ingestion_worker.restore_backup import (
    RestoreBackupError,
    restore_backup,
    validate_restore_inputs,
)


def test_restore_refuses_repository_contained_sql_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    backup = repo / "backup.sql"
    backup.write_text("SELECT 1;")

    with pytest.raises(RestoreBackupError, match="inside the Git repository"):
        validate_restore_inputs(str(backup), "construction_ai_dev", repo_root=repo)


def test_restore_requires_absolute_backup_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(RestoreBackupError, match="must be absolute"):
        validate_restore_inputs("backup.sql", "construction_ai_dev", repo_root=repo)


def test_restore_rejects_unsafe_database_name(tmp_path: Path) -> None:
    backup = tmp_path / "backup.sql"
    backup.write_text("SELECT 1;")

    with pytest.raises(RestoreBackupError, match="database name"):
        validate_restore_inputs(str(backup), "construction-ai-dev;drop", repo_root=tmp_path / "repo")


def test_restore_runs_mysql_without_printing_password(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / "backup.sql"
    backup.write_text("CREATE TABLE demo(id int);")
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stderr="", stdout="")

    settings = Settings(
        MYSQL_HOST="127.0.0.1",
        MYSQL_PORT=3306,
        MYSQL_USER="demo",
        MYSQL_PASSWORD="super-secret",
    )

    result = restore_backup(
        backup_file=str(backup),
        database="construction_ai_dev",
        settings=settings,
        repo_root=repo,
        runner=runner,
    )

    assert result.imported is True
    assert len(calls) == 2
    assert calls[0][0][:2] == ["mysql", "--host"]
    assert "super-secret" not in " ".join(calls[0][0])
    assert calls[0][1]["env"]["MYSQL_PWD"] == "super-secret"
    assert calls[1][1]["stdin"] is not None
    assert result.as_safe_dict()["password"] == "[REDACTED]"


def test_restore_redacts_mysql_errors(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup = tmp_path / "backup.sql"
    backup.write_text("SELECT 1;")

    def runner(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="password=super-secret failed")

    settings = Settings(MYSQL_HOST="127.0.0.1", MYSQL_USER="demo", MYSQL_PASSWORD="super-secret")

    with pytest.raises(RestoreBackupError) as error:
        restore_backup(
            backup_file=str(backup),
            database="construction_ai_dev",
            settings=settings,
            repo_root=repo,
            runner=runner,
        )

    assert "super-secret" not in str(error.value)
    assert "[REDACTED]" in str(error.value)

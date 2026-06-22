from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings


class RestoreBackupError(RuntimeError):
    pass


_DATABASE_RE = re.compile(r"^[A-Za-z0-9_]+$")
_REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class RestoreBackupResult:
    backup_file: str
    database: str
    host: str
    port: int
    created_database: bool
    imported: bool

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "backup_file": self.backup_file,
            "database": self.database,
            "host": self.host,
            "port": self.port,
            "created_database": self.created_database,
            "imported": self.imported,
            "password": _REDACTED,
        }


def run_restore_backup(
    backup_file: str,
    database: str,
    *,
    settings: Settings | None = None,
    repo_root: Path | None = None,
    runner: Any = subprocess.run,
) -> int:
    settings = settings or get_settings()
    repo_root = repo_root or find_repo_root(Path.cwd())
    result = restore_backup(
        backup_file=backup_file,
        database=database,
        settings=settings,
        repo_root=repo_root,
        runner=runner,
    )
    print(json.dumps({"restore": result.as_safe_dict(), "status": "succeeded"}, ensure_ascii=False, indent=2))
    return 0


def restore_backup(
    *,
    backup_file: str,
    database: str,
    settings: Settings,
    repo_root: Path,
    runner: Any = subprocess.run,
) -> RestoreBackupResult:
    backup_path = validate_restore_inputs(backup_file, database, repo_root=repo_root)
    _validate_mysql_restore_settings(settings)
    mysql_base = [
        "mysql",
        "--host",
        settings.mysql_host,
        "--port",
        str(settings.mysql_port),
        "--user",
        settings.mysql_username,
        "--protocol",
        "TCP",
    ]
    env = os.environ.copy()
    if settings.mysql_password:
        env["MYSQL_PWD"] = settings.mysql_password

    create_sql = (
        f"CREATE DATABASE IF NOT EXISTS `{database}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    )
    _run_mysql_command(
        [*mysql_base, "--execute", create_sql],
        env=env,
        runner=runner,
        step="create_database",
    )
    with backup_path.open("rb") as backup_stream:
        _run_mysql_command(
            [*mysql_base, database],
            env=env,
            runner=runner,
            stdin=backup_stream,
            step="import_backup",
        )
    return RestoreBackupResult(
        backup_file=str(backup_path),
        database=database,
        host=settings.mysql_host,
        port=settings.mysql_port,
        created_database=True,
        imported=True,
    )


def validate_restore_inputs(backup_file: str, database: str, *, repo_root: Path) -> Path:
    if not _DATABASE_RE.fullmatch(database):
        raise RestoreBackupError("database name must contain only letters, numbers, and underscores")
    backup_path = Path(backup_file).expanduser()
    if not backup_path.is_absolute():
        raise RestoreBackupError("backup file path must be absolute")
    backup_path = backup_path.resolve()
    if not backup_path.exists():
        raise RestoreBackupError(f"backup file does not exist: {backup_path}")
    if not backup_path.is_file():
        raise RestoreBackupError(f"backup path is not a file: {backup_path}")
    resolved_repo = repo_root.resolve()
    if _is_relative_to(backup_path, resolved_repo):
        raise RestoreBackupError("refusing to restore from a backup file inside the Git repository")
    return backup_path


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def _validate_mysql_restore_settings(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "MYSQL_HOST": settings.mysql_host,
            "MYSQL_USER": settings.mysql_username,
        }.items()
        if not value
    ]
    if missing:
        raise RestoreBackupError("MySQL restore configuration is incomplete: " + ", ".join(missing))


def _run_mysql_command(
    command: list[str],
    *,
    env: dict[str, str],
    runner: Any,
    step: str,
    stdin: Any | None = None,
) -> None:
    try:
        completed = runner(
            command,
            stdin=stdin,
            env=env,
            check=True,
            capture_output=True,
            text=stdin is None,
        )
    except FileNotFoundError as exc:
        raise RestoreBackupError("mysql client executable was not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = _redact(exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr)
        stdout = _redact(exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout)
        message = stderr or stdout or f"mysql command failed during {step}"
        raise RestoreBackupError(f"{step} failed: {message}") from exc
    stderr = getattr(completed, "stderr", "") or ""
    if stderr:
        redacted = _redact(stderr)
        if redacted.strip():
            raise RestoreBackupError(f"{step} produced stderr: {redacted}")


def _redact(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key)=\S+", rf"\1={_REDACTED}", text)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False

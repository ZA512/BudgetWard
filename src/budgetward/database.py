"""Versioned schema initialization; back up SQLite before any schema change."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from .models import Base


def backup_database(source_path: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_path)) as source:
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)


def initialize(engine: Engine, path: Path):
    with engine.connect() as connection:
        version = connection.exec_driver_sql("PRAGMA user_version").scalar()
    if version not in (0, 1, 2, 3):
        raise RuntimeError("Version de base incompatible avec cette application.")
    if version in (1, 2):
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_database(
            path,
            path.parent / "backups" / path.name / "before-migration" / f"v{version}-{timestamp}.db",
        )
    # v2/v3 add tables only; existing account, transaction and rule rows are untouched.
    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        connection.exec_driver_sql("PRAGMA user_version=3")

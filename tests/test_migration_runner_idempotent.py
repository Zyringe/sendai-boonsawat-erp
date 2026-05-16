"""Regression: run_pending_migrations must be idempotent against migration
files that self-insert their own applied_migrations row.

Legacy migration files 025–052 end with
`INSERT INTO applied_migrations(filename, applied_at) VALUES ('NNN_*.sql', ...)`.
On the pending path the runner does `executescript(sql)` (running that
self-insert) and then its OWN bookkeeping insert with the same filename. With a
plain INSERT and `applied_migrations.filename` being PRIMARY KEY, the second
insert raised IntegrityError OUTSIDE the try/except → boot crash for any env
whose applied_migrations is non-empty but missing those files (old backup/seed
restore, staging/CI). Fixed by making the runner's insert `INSERT OR IGNORE`
(matching the bootstrap path). This test reproduces the exact scenario.
"""
import sqlite3

import pytest

import database


def test_runner_survives_self_recording_migration(empty_db, tmp_path, monkeypatch):
    # empty_db = schema clone of live DB (has applied_migrations + brands).
    conn = sqlite3.connect(empty_db)
    conn.row_factory = sqlite3.Row

    # Seed one sentinel row so `applied` is non-empty → runner takes the
    # PENDING path, not the bootstrap-backfill branch.
    conn.execute(
        "INSERT INTO applied_migrations(filename, applied_by) "
        "VALUES ('000_sentinel.sql', 'test')"
    )
    conn.commit()

    # A crafted pending migration that self-inserts (the legacy 025–052 shape).
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    fname = "999_selfrecord_probe.sql"
    (mig_dir / fname).write_text(
        "BEGIN;\n"
        "CREATE TABLE _runner_idemp_probe (id INTEGER);\n"
        "INSERT INTO applied_migrations(filename, applied_at) "
        f"VALUES ('{fname}', datetime('now','localtime'));\n"
        "COMMIT;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(database, "MIGRATIONS_DIR", str(mig_dir))

    # Before the fix this raised sqlite3.IntegrityError (UNIQUE constraint
    # failed: applied_migrations.filename) and aborted boot.
    ran = database.run_pending_migrations(conn, verbose=False)

    assert ran == [fname]
    # exactly one applied_migrations row for the migration (self-insert kept,
    # runner's duplicate OR-IGNOREd) — no crash, no double row
    n = conn.execute(
        "SELECT COUNT(*) FROM applied_migrations WHERE filename=?", (fname,)
    ).fetchone()[0]
    assert n == 1
    # migration body actually executed
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='_runner_idemp_probe'"
    ).fetchone() is not None
    conn.close()

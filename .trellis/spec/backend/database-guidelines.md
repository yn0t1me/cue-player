# Database and Migration Engineering

Applies to SQLAlchemy/SQLite work; extracted 2026-10-21. Entity relationships and operation invariants are defined in [current technical contracts](../contracts/index.md).

## Sessions and transactions

`backend/app/db/session.py` is the engine/session construction authority. It sets check_same_thread=False, Python 3.12 autocommit=False and enables foreign keys on every connection while temporarily switching autocommit. Preserve these behaviors; using a separate bare engine can change integrity behavior.

`backend/app/api/deps.py` yields one session per request. The caller owns commits: VideoRepository.add flushes but does not commit; `save_new_video` in `services/videos.py` supports batch transaction ownership. Services and JobManager delimit writes explicitly. Use a new short-lived session in background work, not a request session retained after response.

`backend/app/services/source_learning.py` demonstrates atomic multi-table publication and concurrent revision checks. Preserve rollback and idempotency at the operation boundary, rather than committing each child row. `backend/tests/test_source_learning_api.py` tests stage failures and concurrent confirmation.

## Shared model infrastructure

Reuse Base naming conventions, IdentityCreated UUIDs, Updated, UTCDateTime and enum_column in `backend/app/db/base.py`. UTCDateTime rejects naive datetimes and returns aware UTC; enum values have database constraints. Tests in `backend/tests/test_database.py` cover timezone roundtrips, uniqueness and FK restrictions.

## Migrations

Schema changes require Alembic revisions under `backend/migrations/versions/`; model metadata alone does not migrate a database. `backend/migrations/env.py` owns database parent creation and migrations; app startup creates the data directory without creating tables (`backend/tests/test_health.py`).

Test upgrades on isolated files, including populated legacy fixtures and unsafe-data rejection. `backend/tests/test_retired_subtitle_migration.py` verifies 014 refuses unsupported rows before changing anything and preserves current child rows. Migration 015 removes notes/questions while preserving marks and their bindings; verify populated upgrades and structure-only downgrade separately. `backend/tests/test_database.py` runs Alembic metadata check. No assumption that every downgrade may discard new data.

Use [shared verification guidance](../guides/project-engineering.md) for isolation. Back up and verify daily data before an explicitly authorized daily migration; a documentation task does not authorize daily data writes.

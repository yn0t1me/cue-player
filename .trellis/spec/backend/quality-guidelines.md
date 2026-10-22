# Backend Verification

Applies to Python backend changes; extracted 2026-10-21.

## Commands and scope

From backend/, use `uv run --locked pytest -q`; `backend/pyproject.toml` defines pytest paths. There is no configured lint/type-check tool in this package. Do not claim Ruff/mypy checks ran or invent them as a prerequisite.

Use the smallest meaningful behavior seam, then the relevant regression scope. Examples:

| Boundary | Existing evidence |
|---|---|
| Settings and startup | `backend/tests/test_config.py`, `test_health.py` |
| Schema/transactions | `test_database.py`, `test_retired_subtitle_migration.py` |
| HTTP/domain publication | `test_video_api.py`, `test_source_learning_api.py` |
| Scheduler/recovery | `test_import_scheduler.py`, `test_import_retries.py` |
| Parsing/normalization | `test_vtt_transcript.py`, `test_normalization_core.py`, `test_source_learning.py` |

Tests use tmp_path, explicit Settings(_env_file=None) where appropriate, DATABASE_URL monkeypatches, migrated SQLite files, TestClient and injected adapters. Follow the test's actual seam; adapter mocks do not prove network availability. For concurrent/background tests, synchronize on observable completion (scheduler.wait_idle is covered for its claim race), not arbitrary short sleeps alone.

## Persistence and evidence

Alembic imports Settings independently, so explicitly isolate DATABASE_URL when invoking migrations even if the app under test receives isolated Settings. See [shared engineering guidance](../guides/project-engineering.md).

For database changes verify schema/data preservation, constraints, rollback and relevant concurrent/idempotent behavior, not only HTTP 200. Record whether tests, isolated integration, daily read checks and real YouTube/STT were executed. Current test counts are results, not permanent acceptance thresholds. Documentation-only checks do not establish a new application regression pass.

# Backend Boundaries and Runtime

Applies to backend engineering; extracted 2026-10-21.

## Existing layers

- `backend/app/main.py`: app factory, lifespan, CORS, shared engine/session factory and scheduler ownership.
- `app/api/routes/`: HTTP parsing, dependencies, status selection and response models. See `videos.py` and `video_collections.py`; routes call services and wake the scheduler after accepted writes.
- `app/schemas/`: Pydantic wire contracts; `app/db/models/`: SQLAlchemy persistence models. Keep these roles distinct.
- `app/services/`: business operations and transaction orchestration. `services/source_learning.py` owns preview/publication; `services/transcript/source_learning.py` owns parsing/time reconstruction; `services/youtube/` owns external adapters.
- `app/repositories/videos.py`: existing simple VideoRepository CRUD seam. Many other services query SQLAlchemy directly; creating a repository for every entity is not an existing universal convention.
- `app/core/`: settings, shared enums and errors; `app/db/`: metadata/session infrastructure; `backend/migrations/`: Alembic history; `backend/tests/`: pytest tests.

Paths starting with app/ above are relative to backend/.

## Runtime ownership

`backend/app/main.py` owns one VideoImportScheduler in lifespan; `services/processing/scheduler.py` consumes persisted pending jobs serially. HTTP requests persist work then wake this consumer, rather than launching competing pipeline runs. `services/processing/video_import.py` coordinates stage claims, external work and result persistence. Blocking operations use asyncio.to_thread; do not hold a write transaction across network/STT work.

Preserve the local single-process FastAPI/SQLite boundary. App-level multi-agent/worker services and multi-process scheduler coordination are not implemented. Development-agent tooling is separate from application architecture. Evidence: `backend/tests/test_import_scheduler.py` and `test_video_import_pipeline.py`.

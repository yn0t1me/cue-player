# Error Boundaries

Applies to HTTP, adapter and processing failures; extracted 2026-10-21.

## HTTP errors

`backend/app/core/errors.py` owns AppError(status_code, code, message) and handlers. Expected business errors use the shape below, represented by `backend/app/schemas/errors.py`:

```json
{"error":{"code":"VIDEO_NOT_FOUND","message":"找不到这个视频，请返回视频库。"}}
```

RequestValidationError becomes a safe 422 VALIDATION_ERROR message selected by request path. Do not return raw request bodies or raw Pydantic exception details as user-facing messages. The current handlers do not define a universal custom envelope for every unhandled exception; do not claim all 500s follow this shape.

## Domain and background failures

`backend/app/services/transcript/source_learning.py` raises SourceLearningError; `services/source_learning.py` translates it into AppError at the application boundary. Preserve distinctions between invalid input, missing evidence and stale/concurrent state rather than converting every failure to the same status. Exact endpoint codes remain in the relevant API contract and tests.

`backend/app/services/processing/video_import.py` maps known adapter errors to safe persistent job codes/messages; unexpected exceptions are logged and turned into a failed stage. Cancellation has explicit cleanup/failure handling. `services/processing/scheduler.py` lets cancellation propagate after settling active work, and contains unexpected processing failures so one bad job does not kill the consumer.

Evidence: `backend/tests/test_video_api.py`, `test_source_learning_api.py` (invalid publication never writes), and `test_import_scheduler.py` (unexpected failure and delayed-claim cancellation). Frontend conversion lives in `frontend/src/api/client.ts`; preserve the code/message boundary across both layers.

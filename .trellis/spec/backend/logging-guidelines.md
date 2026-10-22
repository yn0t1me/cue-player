# Logging and Sensitive Data

Applies to diagnostics and processing failures; extracted 2026-10-21.

## Current implementation

The application uses Python stdlib logging with module loggers (`logging.getLogger(__name__)`). `backend/app/main.py`, `services/processing/video_import.py` and `services/processing/scheduler.py` call logger.exception at unexpected failure/cleanup boundaries. Messages use deferred formatting with internal video identifiers, for example:

```python
logger.exception('Unexpected metadata failure for video %s', video_id)
```

There is no application-wide JSON logger, custom sink/rotation setup, or request correlation system in current code. Uvicorn provides its own server logs. Do not document unimplemented INFO/DEBUG policies as established rules.

## Project data constraints

Follow AGENTS.md and `.gitignore`: secrets, database/media/cache files, logs and work/ artifacts stay outside committed content. Diagnostics use the allowlist in `backend/app/core/config.py::Settings.safe_diagnostics`; it deliberately excludes retired cloud fields. `backend/tests/test_config.py` verifies ignored old cloud secrets do not appear in settings or diagnostics.

When adding logging, retain useful stage/internal IDs and safe error codes. Avoid dumping Settings/env dictionaries, external payload bodies or personal subtitle/note content. Existing logger.exception calls can include third-party exception text; review/redact captured logs before using them as shareable test evidence. This convention is not a claim that automatic global log redaction exists.

# Cross-Layer Change Guide

Applies to Context English changes spanning storage, services, API and React. This project-owned guide replaces Trellis upstream CLI/channel examples; it does not require editing the Trellis runtime.

## Trace the Real Operation

Before implementation, identify the authoritative product behavior, request/response types, persistent invariants and UI consumers. Trace a write from action -> API client -> Pydantic -> service/transaction -> ORM, and its read back to the rendered view. Record the affected paths in the task instead of starting a second progress list.

Examples to inspect:

- Subtitle publication: `frontend/src/features/transcript/LearningTranscriptImportPanel.tsx` -> `frontend/src/api/videos.ts` -> `backend/app/api/routes/videos.py` -> `backend/app/services/source_learning.py`; [publication contract](../contracts/publication.md) owns digest/transaction semantics.
- Favorite selection: `frontend/src/features/transcript/markText.ts` -> API client -> `backend/app/services/transcript_marks.py` -> persisted favorite/key -> refreshed favorites query and separate material output; [anchor contract](../contracts/notes-and-anchors.md) owns identity and concurrency.
- Retry: `frontend/src/features/collections/RetryVideoButton.tsx` -> `backend/app/services/import_retries.py` -> serial scheduler; [processing contract](../contracts/processing-and-retries.md) distinguishes accepted snapshots from current progress.

## Review Questions

- Does the same identity mean video, revision, selection, batch item or job on every side? Do not interchange public YouTube ID and internal UUID.
- Do nullable translation/version/word timing and Unicode code-point offsets survive the full path?
- Does a write need a migration, expected version, idempotency key, writer reservation or related query invalidation? Read the owning contract before deciding.
- Does a late/cancelled operation preserve current data and leave the UI recoverable? Keep filesystem/DB atomicity limits explicit.
- Does the proposed test observe the real failure boundary? Use original rollback/concurrency/lifecycle examples; record separately whether YouTube/AI/STT was exercised.

Tests to locate before editing: `backend/tests/test_source_learning_api.py`, `backend/tests/test_import_retries.py`, `frontend/src/pages/VideoPage.test.tsx`. Run checks appropriate to the actual change; reading this guide does not itself verify behavior.

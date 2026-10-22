# Notes and Selection Contracts

Scope: favorite/question APIs and selection identity, extracted 2026-10-21. User-visible relationships are defined in [notes product spec](../product/notes-and-output.md).

## Request and Response Types

Relative paths below begin at /api/videos/{video_id}.

| Method/path | Body | Success |
|---|---|---|
| GET /marks | none | 200 {items: TranscriptMarkResponse[]} |
| POST /marks | selection plus optional note | 201 new / 200 exact existing favorite |
| PATCH /marks/{mark_id} | {note: string or null}, field required | 200 full favorite |
| DELETE /marks/{mark_id} | none | 204 empty |
| GET /questions | none | 200 {items: TranscriptQuestionResponse[]} |
| POST /questions | selection plus question and optional answer | 201 full question; no selection deduplication |
| PATCH /questions/{question_id} | question and/or answer; nonempty patch | 200 full question |
| DELETE /questions/{question_id} | none | 204 empty |

Selection = {revision_id,segment_id,start_offset,end_offset,selected_text}. IDs are nonempty strings up to 36 chars; strict integer offsets are 0<=start<end, each bounded by 1,000,000 (end positive). Request models forbid extras and are strict. selected_text must be nonempty, nonblank and equal the exact original-English slice. Note max 10,000 chars; empty/blank note becomes null. Question is nonblank 1–10,000 chars; answer is nullable up to 100,000 chars and blank normalizes to null. PATCH omission preserves a field; explicit null is accepted only for answer, not question. Anchors cannot be patched.

Responses share id/video_id/revision_id/revision_number/revision_origin/is_current/segment_id/segment_sequence_index/segment_start/segment_end/segment_text/start_offset/end_offset/selected_text/created_at/updated_at. Favorite adds note; question adds question/answer. No has_saved_answer or canonical-binding table is exposed. List current revision first, older revisions descending, then segment time/sequence, position, creation/id.

## Unicode and Concurrency

Offsets are Unicode code points in a half-open range, not UTF-16 code units, graphemes, byte offsets or displayed chunk positions. `frontend/src/features/transcript/markText.ts` converts DOM text using Array.from and verifies the slice; backend Python len/slicing validates it. Chunk separators preserve the original single space and Chinese is outside the selectable English root. Repeated equal words require the exact position.

Creation acquires the same per-video SQLite writer lock as subtitle publication, then checks current revision, video/segment membership and selection. Stale revision is 409 TRANSCRIPT_REVISION_CONFLICT; foreign/missing segment is 404 TRANSCRIPT_SEGMENT_NOT_FOUND; mismatch is 422 MARK_SELECTION_INVALID. Missing video is 404 VIDEO_NOT_FOUND, unavailable notes context is 409 TRANSCRIPT_UNAVAILABLE; foreign/missing record is TRANSCRIPT_MARK_NOT_FOUND or TRANSCRIPT_QUESTION_NOT_FOUND. Shape errors are 422 VALIDATION_ERROR, with safe text. Updating/deleting an existing historical record preserves its original anchor rather than applying creation's current-only selection gate.

## Canonical Favorite and First Answer

Create/reuse via transcript_mark_keys inside the writer transaction; a quick duplicate never overwrites a note. Answer saving calls _collect_first_answer in the question service: only the first nonblank save when has_saved_answer=false creates/reuses the same selection's favorite and records the durable event. Favorite creation, question/answer and first-save fact commit together or roll back. Historical question answers can favorite their original old-version anchor; this internal operation does not relax public creation checks.

Clearing/refilling an old answer or editing it after cancelling a favorite does not retrigger. A different question's first answer can trigger again. Delete/clear/read operations do not fabricate those events. First-save migration history must not reconstruct deliberately cancelled favorites.

Evidence: `backend/app/schemas/transcript_marks.py`, `backend/app/schemas/transcript_questions.py`, `backend/app/services/transcript_marks.py`, `backend/app/services/transcript_questions.py`; `backend/tests/test_video_api.py` covers exact Unicode positions, concurrent creation/publication, historical bindings and atomic first-answer behavior. Frontend selection/format tests remain in `frontend/src/features/transcript/markText.test.ts` and `collectionOutput.test.ts` (same directory). Content export is frontend-only and does not add an API write.

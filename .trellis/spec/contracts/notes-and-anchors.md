# Favorite Selection Contracts

Updated 2026-10-22. This document owns the reduced favorite HTTP/selection contract. [Product output](../product/notes-and-output.md) owns user-visible export behavior.

## 1. Scope / Trigger

Removal of personal notes/questions/answers changes the HTTP request/response shapes and persistence schema. Keep exact favorite anchors and historical context; no compatibility API for retired fields remains.

## 2. Signatures

Paths are relative to /api/videos/{video_id}.

| Method/path | Body | Success |
|---|---|---|
| GET /marks | none | 200 {items: TranscriptMarkResponse[]} |
| POST /marks | selection | 201 new / 200 exact existing favorite |
| DELETE /marks/{mark_id} | none | 204 empty |

PATCH /marks/{mark_id} and all /questions routes are absent. Framework method-not-allowed/not-found behavior applies; no retired endpoint returns success. Schema 015 removes transcript_marks.note and transcript_questions, retaining transcript_mark_keys and all favorite anchors. Migration history still contains the original definitions.

## 3. Contracts

Selection = {revision_id,segment_id,start_offset,end_offset,selected_text}. IDs are nonempty strings of at most 36 chars; strict integer offsets satisfy 0<=start<end, each bounded by 1,000,000 (end positive). Request models forbid extras, including note. selected_text is nonblank and equals the exact original English slice.

Response fields: id,video_id,revision_id,revision_number,revision_origin,is_current,segment_id,segment_sequence_index,segment_start,segment_end,segment_text,start_offset,end_offset,selected_text,created_at,updated_at. No note/question/answer is exposed. API lists current edition first, older editions descending, then segment time/sequence/position/creation/id; Agent output separately orders by video appearance.

Offsets are Unicode code points in a half-open range, not UTF-16 units, bytes or displayed chunk positions. Frontend markText.ts uses Array.from; Python slicing validates the same text. Chinese and chunk separators cannot become selected English content. No environment variable changes are required.

Creation acquires the video's SQLite writer lock shared with publication, validates current revision and ownership, then creates/reuses the canonical favorite binding within one transaction. The key is (video_id,revision_id,segment_id,start_offset,end_offset); mark_id is unique. Removing the canonical favorite rebinds an eligible duplicate by stable creation/id ordering, or removes the key before deleting the row. It never performs question bookkeeping. Existing historical favorites can be read/deleted without relaxing current-only creation.

## 4. Validation & Error Matrix

| Condition | Result |
|---|---|
| Missing video | 404 VIDEO_NOT_FOUND |
| Unavailable transcript | 409 TRANSCRIPT_UNAVAILABLE |
| Stale creation revision | 409 TRANSCRIPT_REVISION_CONFLICT |
| Missing/foreign segment | 404 TRANSCRIPT_SEGMENT_NOT_FOUND |
| Invalid slice/blank selection | 422 MARK_SELECTION_INVALID |
| Missing/foreign favorite | 404 TRANSCRIPT_MARK_NOT_FOUND |
| Shape error, including legacy note field | 422 VALIDATION_ERROR with safe text |
| Retired question route / note PATCH | Framework 404 / 405 as applicable |

## 5. Good / Base / Bad Cases

- Good: create a current Unicode selection, publish a new transcript, and export the favorite's original subtitle entry unchanged.
- Base: exact duplicate create returns the existing favorite, and cancellation deletes that favorite without changing the transcript.
- Bad: submit a stale selection or note field, reinterpret UTF-16 units as code points, or silently use current text for an old favorite.

## 6. Tests Required

`backend/tests/test_video_api.py` covers Unicode, exact identity, stale/concurrent publication, duplicate creation, historical context/deletion and retired endpoint/field rejection. Migration tests must prove populated 014->015 preserves marks/keys and non-retired tables while removing note/question data, passes FK/integrity and metadata checks. Frontend markText, collectionOutput and page/selection tests cover anchor/output flow. Agent export is frontend-only and adds no write API.

## 7. Wrong vs Correct

Wrong: POST an old note field, accept it silently, and treat its removal as a UI-only change. Correct: remove the field from client/types/schema/storage, reject extras, and retain only the exact favorite selection and its original context.

# Publication Identity and Atomicity

Extracted: 2026-10-21. Current publication contract; legacy SRT/cloud publication is retired. Source: `backend/app/services/source_learning.py`, `backend/app/services/chunk_layouts.py` and `backend/app/services/transcript/source_learning.py`.

## Distinct Identities

- Source digest binds source format/video/type/mode/extractor and complete ordered local evidence including text/times/location; file locators include original file hash. It excludes current revision, so changing the reading edition alone does not change original source identity.
- Preview digest binds requested base revision, source digest/extractor, each range's start/end in ms, canonical English, boundaries, result format/type/mode and translations.
- Stored revision content_sha256 is only canonical [start_ms,end_ms,English] rows. It is a fast equality filter, **not** full candidate identity; it excludes Chinese and source evidence.
- Layout digest binds revision_id plus ordered segment IDs and boundary offsets. It is not reusable across revisions merely because English matches.

## Confirmation

POST source-learning accepts the same result text plus expected_revision_id and preview_digest. Acquire the video's SQLite write lock before reading/rebuilding. Reread original source, rebuild and check digest against expected_revision_id. Mismatch is 409 SOURCE_LEARNING_PREVIEW_MISMATCH. Then inspect current revision.

If current origin=source_aligned, English/timing digest and row count match, `_matches` also requires segment video/order, source_units type, null normalization_version/run, exact persisted source_refs (including result format/type/mode and locator evidence), ms times, English, translation and boundary offsets. Only full equality returns existing transcript/layout without a new revision. This check occurs before base-current conflict, allowing identical concurrent/replayed confirmation to converge.

Otherwise current revision must equal expected_revision_id or reject 409 TRANSCRIPT_REVISION_CONFLICT. Allocate next per-video revision_number under the same lock; insert source_aligned revision, segments with translation/source_units evidence/explicit null version, one layout and all segment boundaries, switch Video.current_revision_id and commit once. Return {transcript,chunk_layout} referencing the same revision. A changed translation/source/range/layout is not swallowed by English-only hash equality. Failure at any stage rolls back all artifacts and pointer changes; preview/cancel never publishes.

## Evidence Retention

Per-segment source_refs contains extractor_version,source_digest,first/last_unit_id,units,start_basis,end_basis,result_format,source_type,processing_mode. Units retain original cue ID or file hash, cue/line/token/character position, start/end basis and optional end_cue_sequence_index; no fake UUID is substituted for a file locator. Original Raw and favorite anchors are untouched. Current reads do not expose internal source_refs.

Layout GET is readonly; a separate layout-write API does not exist. Historical revision reads do not change the current pointer. English learning SRT exports only current English/times; Raw SRT comes from original cues through its export rules, not this publication.

Evidence: `backend/tests/test_source_learning_api.py` covers stage-by-stage rollback, concurrent identical/different confirmation, translation-only changes, evidence mismatch and readonly preview; `backend/tests/test_video_api.py` covers historical favorites and publication concurrency. These are code/test-source facts, not rerun verification or a universal quality guarantee.

# Collection, Preview and Batch Contracts

Extracted: 2026-10-21. Current schema types: `backend/app/schemas/video_collections.py`; operations: `backend/app/services/video_collections.py` and `backend/app/services/video_imports.py`. Product flow is separate from these engineering choices.

## Collection Writes

POST collection {name,description?}; name is trimmed 1–200 chars, description nullable up to 2000. PATCH accepts name/description plus expected_version; at least one change field is required, explicit name:null is rejected, description:null clears it. Member add accepts {video_ids,expected_version}, 1–200 IDs. Reorder accepts {item_ids,expected_version}, up to 10,000 IDs and must specify the complete unique current set. DELETE collection/member takes expected_version as query parameter. Body versions are strict integers >=1; body extras are forbidden.

Collection response = id,name,description,version,source_playlist_id,source_playlist_url,created_at,updated_at,thumbnail_url,total_count,ready_count; detail adds items[{id,position,video:VideoResponse}]. List wraps {items}. Positions are zero-based. Writer reservation precedes version/dedup reads. Effective writes bump version; unchanged duplicate membership does not. Remove compacts positions; reorder uses temporary positions outside the current range before writing the new sequence, in one transaction. Missing IDs are 404 COLLECTION_NOT_FOUND / COLLECTION_ITEM_NOT_FOUND; stale versions 409 COLLECTION_VERSION_CONFLICT. Frontend refreshes conflicts without automatically replaying stale order.

## Preview

POST /api/video-import-previews receives {input_kind:single|multiple|playlist,urls:[string]}, 1–200 URLs of 1–2048 chars; non-multiple modes require exactly one URL. Response {id,expires_at,limits,source,items,duplicate_count}; limits {max_items:200,expires_in_seconds:1800}; source has input_kind,nullable playlist_id/url/title. Item has id,source_position,youtube_video_id,url,title,duration,thumbnail_url,selectable,existing_video_id,error; optional metadata may be null. Error is safe {code,message}.

Multi-link preview parses locally and reuses saved metadata; new video metadata waits for actual import. Playlist extraction uses a child process (45s deadline, kill/reap on cancellation); process-level semaphore allows two previews, with 50s total budget including wait. Client preview timeout is 60s. Upstream flat extraction rejects warnings/incomplete/mismatched playlist identity and consumes at most 201 source entries to detect a >200 list, before deduplication. No cookies/media/subtitle/thumbnail/infojson download is added. Empty preview is allowed but empty submission is not.

Preview persists a 30-minute snapshot without creating videos/jobs/collections. It has no automatic expiry cleanup. Unavailable entries stay visible/nonselectable; absent metadata alone does not prove unavailability. Parse/fetch/limit failures use safe errors, not raw upstream exception bodies. `backend/app/services/youtube/playlists.py` is the exact adapter authority.

## Batch Submission and Read

POST /api/video-import-batches receives {preview_id,selected_item_ids,subtitle_preference,target,idempotency_key}. Selection has 1–200 unique selectable snapshot IDs, ordered explicitly. Target is discriminated: {kind:none}, {kind:existing,collection_id}, or {kind:new,name,description?}; key is 1–100 chars. Persist batch, new videos/jobs, destination/members and snapshot outcomes atomically before waking processing. Unavailable entries are appended after ordered selection and create no video/job.

Idempotency is global for batch keys: same key + same canonical request digest (including selection order, excluding key) returns 200 current read of the original batch, even after preview expiry. Same key/different digest is 409 IDEMPOTENCY_CONFLICT. New batch returns 202. Invalid selection is 422 IMPORT_SELECTION_INVALID, missing preview 404 IMPORT_PREVIEW_NOT_FOUND, expired preview 409 IMPORT_PREVIEW_EXPIRED. Concurrent distinct submissions still converge on video/member identity.

BatchResponse = id,preview_id,collection_id,collection_name_snapshot,subtitle_preference,created_at,status,counts,items. Status is pending/running/completed/completed_with_errors. Counts total/ready/waiting/running/failed/unavailable sum to total. Item has id,preview_item_id,position,youtube_video_id,disposition (created/reused/already_member/unavailable),video,job,error. video contains the current latest job; item.job uses explicit retry binding first, original created job second, otherwise current job for reused/already_member. These can intentionally differ. Status prioritizes running, then waiting, then terminal errors/unavailable, otherwise complete. Inconsistent data is not counted ready.

Batch GET is dynamic, unlike retry POST acceptance snapshots. Collection deletion leaves a null collection_id and retained name snapshot. There is no batch-history-list endpoint or persistent browser recovery of an unanswered submission key after refresh. Explicit batch retries are defined in [processing](processing-and-retries.md).

Evidence: `backend/tests/test_video_collections_api.py`, `test_youtube_playlists.py`, `test_import_retries.py`, `test_import_scheduler.py`; `frontend/src/features/collections/Collections.test.tsx`, `frontend/src/api/collections.ts` and `frontend/src/features/collections/shared.ts` (IntentKey). Read source; no new playlist network run is implied.

# HTTP API

Scope: current application routes and shared wire behavior, updated 2026-10-22. Engineering baseline, verified by source inspection. All paths below include the /api prefix registered in `backend/app/main.py`.

## Shared Shapes

`backend/app/schemas/videos.py` defines VideoResponse: id, youtube_video_id, youtube_url, nullable title/channel_title/duration_seconds/thumbnail_url, status, subtitle_preference, nullable subtitle_source/subtitle_language, created_at and nullable processing. ProcessingJobResponse has id, stage, status, progress, nullable error_code/error_message. It does not expose database timestamps or source payloads. Latest job is selected by created_at DESC, id DESC (`backend/app/repositories/videos.py`). Lists use {items: [...]}; the video library is currently unpaginated, ordered created_at DESC, id DESC.

ImportVideoRequest accepts url (trimmed, 1–2048 characters) and subtitle_preference (manual_first default, or auto_only), with extras forbidden. URL parsing accepts supported http(s) YouTube watch/shorts/embed and youtu.be links, canonicalizes the 11-character public video ID and stores https://www.youtube.com/watch?v={id}; alternate URL spelling/t/list does not create a second identity. See `backend/app/services/youtube/parser.py` and `backend/tests/test_youtube_parser.py` for host/port/duplicate-v rules. New video and pending job commit atomically; a duplicate including a failed video reuses the saved record without a new job or source change. Both return {already_exists,video,job}; job corresponds to video.processing.

`backend/app/schemas/transcripts.py` defines TranscriptResponse {video_id,revision_id,origin,normalization_version,segments}; each segment has id,sequence_index,start,end,text,translation_zh (nullable). Times are seconds, ordered by sequence_index. Version is 2 for generated segments and null for source-aligned ones; no Raw/source_refs/local paths are returned. A missing video is 404 VIDEO_NOT_FOUND, processing is 409 TRANSCRIPT_NOT_READY, failed/missing/unreadable current revision is 409 TRANSCRIPT_UNAVAILABLE. Historical read uses the same shape, requires an available current transcript first, and rejects another video's revision with 404 TRANSCRIPT_REVISION_NOT_FOUND. Revision list items have id,origin,revision_number,created_at,normalization_version,segment_count,is_current.

ChunkLayoutStateResponse is {video_id,revision_id,layout}, with null layout when absent. A layout has id,revision_id,content_sha256,created_at,updated_at,segments; each segment has segment_id,sequence_index,start,end,text,boundary_offsets,chunks. Definitions: `backend/app/schemas/chunk_layouts.py` and `backend/app/services/chunk_layouts.py`.

## Route Catalog

The table is a source snapshot, checked against route definitions rather than a promise of new endpoints. Success codes are default/explicit route codes plus explicitly declared replay/duplicate codes. Plain dict and SRT routes are described in their topic; no declared response_model does not mean no response contract.

| Method and path | Success | Declared response |
|---|---|---|
| `GET /api/health` | 200 | HealthResponse |
| `GET /api/collections` | 200 | CollectionListResponse |
| `POST /api/collections` | 201 | CollectionDetailResponse |
| `GET /api/collections/{collection_id}` | 200 | CollectionDetailResponse |
| `PATCH /api/collections/{collection_id}` | 200 | CollectionDetailResponse |
| `DELETE /api/collections/{collection_id}` | 204 | empty (204) |
| `POST /api/collections/{collection_id}/items` | 200 | CollectionDetailResponse |
| `DELETE /api/collections/{collection_id}/items/{item_id}` | 204 | empty (204) |
| `PATCH /api/collections/{collection_id}/order` | 200 | CollectionDetailResponse |
| `POST /api/video-import-previews` | 200 | PreviewResponse |
| `POST /api/video-import-batches` | 202 / 200 | BatchResponse |
| `GET /api/video-import-batches/{batch_id}` | 200 | BatchResponse |
| `POST /api/video-import-batches/{batch_id}/retry` | 202 / 200 | RetryBatchResponse |
| `POST /api/videos` | 202 / 200 | ImportVideoResponse |
| `POST /api/videos/{video_id}/retry` | 202 / 200 | RetryVideoResponse |
| `GET /api/videos` | 200 | VideoListResponse |
| `GET /api/videos/{video_id}` | 200 | VideoResponse |
| `GET /api/videos/{video_id}/transcript` | 200 | TranscriptResponse |
| `GET /api/videos/{video_id}/transcript/export.srt` | 200 | English SRT |
| `GET /api/videos/{video_id}/transcript/revisions` | 200 | {items: revision summaries} |
| `GET /api/videos/{video_id}/transcript/revisions/{revision_id}` | 200 | TranscriptResponse |
| `GET /api/videos/{video_id}/transcript/chunk-layout` | 200 | ChunkLayoutStateResponse |
| `GET /api/videos/{video_id}/marks` | 200 | TranscriptMarkListResponse |
| `POST /api/videos/{video_id}/marks` | 201 / 200 | TranscriptMarkResponse |
| `DELETE /api/videos/{video_id}/marks/{mark_id}` | 204 | empty (204) |
| `GET /api/videos/{video_id}/transcript/learning-source` | 200 | learning-source-v2 |
| `POST /api/videos/{video_id}/transcript/source-learning/preview` | 200 | SourceLearningPreviewResponse |
| `POST /api/videos/{video_id}/transcript/source-learning` | 200 | LearningPublishResponse |
| `GET /api/videos/{video_id}/transcript/learning-export.srt` | 200 | English SRT |

## Errors and Specialized Requests

Expected AppError uses {error:{code,message}}; request validation becomes 422 VALIDATION_ERROR without echoing user content. Unknown routes and method mismatches keep framework behavior; there is no universal custom envelope for all infrastructure/unhandled 500s. See `backend/app/core/errors.py` and `backend/app/schemas/errors.py`.

- Favorite selection bodies, limits and statuses: [anchors](notes-and-anchors.md).
- Collection/preview/batch bodies and statuses: [collections](collections-and-batches.md).
- Single/batch retry requests, accepted snapshots, per-item conflict behavior: [processing](processing-and-retries.md).
- Source copy/preview/publish bodies, result format, validation codes: [source exchange](source-exchange.md), [publication](publication.md).

Health is only {status:"ok"}; it checks neither persistence nor YouTube. Raw and current-learning exports are English SRT downloads with attachment names; the first reads Raw, the second current learning text. Exact export formatting lives in `backend/app/services/srt_export.py` and source_learning.py; no bilingual SRT endpoint exists.

## Retired Routes

Question GET/POST/PATCH/DELETE routes and favorite-note PATCH are removed. Favorite create accepts only the selection and responses contain no note. Agent material copy/Markdown is frontend-only and adds no endpoint.

Legacy transcript import/learning-import/chunk-layout POST preview/writes and normalization GET/POST/batch-retry routes do not exist. Missing routes return 404; POST to the retained chunk-layout GET path returns 405. Do not restore NORMALIZATION_DISABLED responses or accept JSON v1 results. Failure-import retry is the current retry route, separate from retired cloud-batch retry. Source-switch transcript/reprocess is not implemented.

Evidence: `backend/app/api/routes/videos.py`, `video_collections.py` in the same directory and `health.py`; `backend/tests/test_video_api.py`, `test_source_learning_api.py`, `test_video_collections_api.py`. Source inspection is not an executed HTTP acceptance run.

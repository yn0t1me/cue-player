# Persistence Model

Scope: current ORM relationships and operation invariants, updated 2026-10-22. Current schema is the Alembic 015 line; the historical migration chain is still needed to build/upgrade a database. Documenting this model does not perform a schema or data migration.

## Source Inventory

All tables below are declared in `backend/app/db/models/`. Column lists show locally declared mapped fields; shared id/created_at/updated_at mixins apply where inherited. Types, nullability, defaults and constraints remain explicit in the linked model definitions; use `backend/app/db/base.py` for UUID, aware UTC and enum naming conventions. Schema evolution requires migrations, not Markdown edits.

| Table | Declared columns (shared mixins omitted) | Model authority |
|---|---|---|
| `processing_jobs` | video_id, stage, status, progress, error_code, error_message, started_at, finished_at | [ProcessingJob](../../../backend/app/db/models/processing_job.py) |
| `raw_transcript_cues` | video_id, sequence_index, start_seconds, end_seconds, text, source_type, source_payload | [RawTranscriptCue](../../../backend/app/db/models/transcript.py) |
| `raw_transcript_words` | video_id, cue_id, sequence_index, text, start_seconds, end_seconds, confidence | [RawTranscriptWord](../../../backend/app/db/models/transcript.py) |
| `transcript_revisions` | video_id, origin, revision_number, content_sha256 | [TranscriptRevision](../../../backend/app/db/models/transcript.py) |
| `learning_transcript_segments` | video_id, revision_id, sequence_index, text, translation_zh, start_seconds, end_seconds, source_ref_type, source_refs, normalization_version, normalization_run_id | [LearningTranscriptSegment](../../../backend/app/db/models/transcript.py) |
| `transcript_normalization_runs` | video_id, job_id, method, normalization_version, input_unit_count | [TranscriptNormalizationRun](../../../backend/app/db/models/transcript.py) |
| `transcript_chunk_layouts` | video_id, revision_id, content_sha256 | [TranscriptChunkLayout](../../../backend/app/db/models/transcript_chunk_layout.py) |
| `transcript_chunk_segments` | layout_id, segment_id, boundary_offsets | [TranscriptChunkSegment](../../../backend/app/db/models/transcript_chunk_layout.py) |
| `transcript_marks` | video_id, revision_id, segment_id, start_offset, end_offset, selected_text | [TranscriptMark](../../../backend/app/db/models/transcript_mark.py) |
| `transcript_mark_keys` | video_id, revision_id, segment_id, start_offset, end_offset, mark_id | [TranscriptMarkKey](../../../backend/app/db/models/transcript_mark_key.py) |
| `videos` | youtube_video_id, youtube_url, title, channel_title, duration_seconds, thumbnail_url, status, subtitle_source, subtitle_preference, subtitle_language, current_revision_id | [Video](../../../backend/app/db/models/video.py) |
| `video_collections` | name, description, source_playlist_id, source_playlist_url, version | [VideoCollection](../../../backend/app/db/models/video_collection.py) |
| `video_collection_items` | collection_id, video_id, position | [VideoCollectionItem](../../../backend/app/db/models/video_collection.py) |
| `video_import_previews` | input_kind, source, items, duplicate_count, expires_at | [VideoImportPreview](../../../backend/app/db/models/video_collection.py) |
| `video_import_batches` | preview_id, idempotency_key, request_digest, subtitle_preference, collection_id, collection_name_snapshot | [VideoImportBatch](../../../backend/app/db/models/video_collection.py) |
| `video_import_batch_items` | batch_id, preview_item_id, position, youtube_video_id, video_id, job_id, disposition, error_code, error_message | [VideoImportBatchItem](../../../backend/app/db/models/video_collection.py) |
| `video_import_retry_requests` | target_kind, target_id, idempotency_key, request_digest, response_payload | [VideoImportRetryRequest](../../../backend/app/db/models/video_collection.py) |
| `video_import_retry_bindings` | batch_item_id, job_id | [VideoImportRetryBinding](../../../backend/app/db/models/video_collection.py) |

## Identity and Ownership

Video identity is unique youtube_video_id, while local video IDs own media paths and relationships. One video owns multiple jobs/revisions, one preserved Raw source set, and favorites; collections reference the same video rather than copying these entities. Raw cues/words are unique on (video_id,sequence_index), words may refer to a cue and have nullable actual times/confidence. Learning segments are unique on (revision_id,sequence_index), not globally by video/sequence.

TranscriptRevision permits only generated/source_aligned, unique (video_id,revision_number) with positive numbering. Generated segments use normalization_version=2, source_ref_type=cue, source_refs.cue_ids and the deterministic run relation. Source-aligned segments use normalization_version=NULL (explicit SQL null on insertion), source_ref_type=source_units and source evidence JSON, with no generation run. The segment check constrains version/ref-type combinations; consistency with revision origin/video is additionally enforced by services. Do not claim every cross-row semantic relationship is a DB constraint.

Video.current_revision_id is an indexed nullable string, **not an ORM foreign key**; transcript reads/publication validate that the referenced revision belongs to the video. New publication creates new segment IDs and switches that pointer atomically; old favorite anchors remain attached to the original revision/segment. Revision deletion is restricted by dependent records; no periodic automatic history cleanup is defined.

## Favorites and Layouts

Favorite anchors store video/revision/segment IDs plus Unicode code-point offsets and exact selected text. The canonical favorite binding key is (video_id,revision_id,segment_id,start_offset,end_offset); mark_id is unique. Historical duplicate mark rows can remain. Deleting the bound mark reassigns to an eligible historical duplicate by creation/id ordering or removes the binding before deletion. Personal notes, questions, answers and first-answer bookkeeping are retired. See [anchor operations](notes-and-anchors.md).

A revision has at most one TranscriptChunkLayout. Per-layout segment association is unique; boundary_offsets is JSON. Deleting a layout cascades its chunk rows; segment and favorite references use RESTRICT. Layout content_sha256 binds revision and segment IDs plus offsets, rather than English text alone. [Publication](publication.md) owns transaction/identity rules.

## Collections and Retry History

Collection members enforce unique (collection_id,video_id) and (collection_id,position), nonnegative positions; collection version is positive. Collection deletion cascades memberships and sets batch collection_id NULL, preserving its name snapshot, videos and jobs. Preview and batch references are restricted as modeled; expired previews are not automatically pruned by the current service.

Batch idempotency_key is globally unique in video_import_batches. Retry request keys are instead unique per (target_kind,target_id,idempotency_key), with request digest and accepted response JSON. Retry binding has one row per batch item and RESTRICTs its job. Original batch created-job references remain; bindings select the last accepted explicit retry for that item. [Collections](collections-and-batches.md) and [processing](processing-and-retries.md) define dynamic progress reads.

## Migration and Verification

`backend/migrations/versions/014_retire_legacy_subtitles.py` removes legacy model-only structures and rejects incompatible rows before altering them. Migration 015 intentionally drops transcript_questions and transcript_marks.note under the approved product change, preserving all favorites/keys and other current rows. Native SQLite DROP COLUMN avoids rebuilding the referenced marks table. Downgrade restores structure only, never deleted content; use a consistent pre-upgrade backup for content recovery. Historical 001–014 definitions remain necessary for fresh builds and migration tests. Nonempty collection/retry data may block earlier lossy downgrades; inspect the relevant migration before claiming reversibility.

Evidence: `backend/tests/test_database.py`, `test_retired_subtitle_migration.py`, `test_source_learning_api.py` and `test_video_api.py`; [database engineering](../backend/database-guidelines.md) owns isolation/backup practice. Current business tables contain no Chapter/StudySet/LearningItem/AIAnswer/PracticeAttempt schema.

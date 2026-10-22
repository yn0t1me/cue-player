# Job Lifecycle, Restart and Retry

Extracted: 2026-10-21. Exact transitions: `backend/app/services/processing/job_manager.py`; consumer: `backend/app/services/processing/scheduler.py`; retry: `backend/app/services/import_retries.py`.

## Stages and Transaction Handoffs

Video status is processing/ready/failed; job status is pending/running/completed/failed. Stage/progress checkpoints:

| Stage | Progress / meaning |
|---|---|
| fetching_metadata | pending 0, claim runs metadata; successful handoff to caption pending 10 |
| fetching_captions | 10 discovers/downloads; 35 means saved VTT awaiting Raw parse |
| downloading_audio | 20, only established STT path |
| transcribing | 40, local model work |
| normalizing | 80, atomic Raw save complete; generate locally then publish |
| completed | stage/status completed, progress 100; video ready |
| failed | stage/status failed, safe code/message and finished_at; existing progress remains diagnostic |

Claim checks expected stage/status/video/job and obtains writer reservation before read/write. Blocking/network/model work happens outside DB write transactions. Result save validates that the job still owns the stage and commits a short handoff; late completion cannot resurrect failed work. started_at is set on first claim including non-metadata retry checkpoints. Initial publication commits revision/segments/run, current pointer, Video.ready and Job.completed together; see [pipeline](transcript-pipeline.md).

Lifespan owns one serial consumer. Requests commit work and wake it; next_pending_job orders legal pending work by created_at,id. One-second scans recover lost wake notifications. This is one-process coordination, not a multi-process distributed queue. Scheduler errors settle active work or back off; cancellation during claim must still produce an interruption result. Existing wait_idle helper accounts for a pending job being claimed during its query and is test synchronization, not HTTP waiting.

## Restart and Stop

Startup cleans stale managed staging and calls recover_after_restart. Running normalizing/80 can return to pending only when Video.processing, no learning row for the video and no normalization run for that job. Other running work becomes PROCESS_INTERRUPTED and audio is cleaned; cleanup failure can replace the safe failure code. Pending legal stages resume through the consumer. Old failed jobs do not gain a new job automatically. Normal shutdown cancels active work and cleans managed audio, leaving queued pending work. Recovery is narrower than arbitrary source integrity repair.

## Retry Admission and Checkpoint

POST /api/videos/{video_id}/retry {expected_job_id,idempotency_key} returns first 202 / replay 200 {video_id,previous_job_id,job}. Require Video.failed, exact latest failed expected job, no pending/running job, no current pointer and no learning/revision/normalization-run residue. Reject changed state as VIDEO_RETRY_CONFLICT; unsafe evidence as RETRY_EVIDENCE_CONFLICT (both 409). Preserve old job, Raw/file identity and saved preference.

| Evidence | New pending checkpoint |
|---|---|
| Consistent nonempty Raw, source/language, old progress 80, valid continuous cue/word ordering and references | normalizing/80, reuse Raw IDs |
| Caption source/language, valid managed VTT, no Raw, old progress 35 | fetching_captions/35, parse original file |
| Fixed STT source, no Raw/VTT, old progress 20/40 | downloading_audio/20; do not reselect captions |
| No source/language, no Raw/VTT, old progress 0/10/20/40 | fetching_metadata/0 |
| Orphan words/products, missing/mismatched source, invalid file/order/times, missing Raw at old80 | reject; do not delete evidence to bypass |

For existing caption Raw, available VTT must match parse_vtt cue/payload data; missing VTT is allowed only when the Raw checkpoint itself is complete and consistent. STT Raw cannot coexist with caption VTT. Validate nullable actual word times/confidence, cue membership, sequence and content. Progress80 attests to the original atomic handoff, not detection of every possible manually forged database state. Managed temporary audio may be cleaned; Raw/VTT/learning/history must not be overwritten. New job created_at is strictly later than the old latest job (and no earlier than now).

## Retry Idempotency and Batch Binding

POST /api/video-import-batches/{batch_id}/retry receives {item_ids,expected_job_ids,idempotency_key}. 1–200 unique item IDs; expected_job_ids maps exactly those IDs to expected job IDs or null. Foreign batch items cause 422 IMPORT_SELECTION_INVALID; invalid shape is 422 VALIDATION_ERROR. First response 202 even if no item is accepted; replay 200. Response {batch_id,items:[{item_id,video_id,previous_job_id,status,job,error}]} with accepted/skipped/rejected.

Retries use unique (target_kind,target_id,key), canonical request digest and persisted accepted response snapshot. Same key/digest returns the original acceptance, not live job progress; same key/different request is 409 IDEMPOTENCY_CONFLICT. Follow GET video/batch for current status. New job, Video.processing, accepted item bindings and replay record commit together. Batch uses nested transactions for known per-item rejections, preserving other valid items; unexpected infrastructure errors roll back, not masquerade as business rejects.

Item binding pins its latest explicitly accepted retry job; original created-job references and other batches do not change. Unavailable items skip; changed binding/latest job or unsafe evidence rejects; an expected job that is no longer failed can skip. A single-video retry never changes batch bindings. Client session keeps a stable key for the same intent but does not replace server persistence.

Evidence: `backend/tests/test_import_retries.py`, `test_import_scheduler.py`, `test_video_import_pipeline.py` and `test_database.py`; no retry endpoint accepts source-switch/Reprocess parameters.

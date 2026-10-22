"""Explicit first-import retries preserve source evidence and old jobs."""
from datetime import UTC, datetime, timedelta
import hashlib
import json
from math import isfinite
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import JobStatus, ProcessingStage, SubtitleSource, VideoStatus
from app.core.errors import AppError
from app.db.models import (
    LearningTranscriptSegment, ProcessingJob, RawTranscriptCue, RawTranscriptWord,
    TranscriptNormalizationRun, TranscriptRevision, VideoImportBatch, VideoImportBatchItem,
    VideoImportRetryBinding, VideoImportRetryRequest,
)
from app.repositories.videos import VideoRepository
from app.schemas.video_collections import (
    PreviewError, RetryBatchItemResponse, RetryBatchRequest, RetryBatchResponse,
    RetryVideoRequest, RetryVideoResponse,
)
from app.schemas.videos import ProcessingJobResponse
from app.services.processing.audio_store import AudioStore
from app.services.processing.caption_store import CaptionStore
from app.services.transcript import parse_vtt
from app.services.video_collections import acquire_import_write_lock


def _conflict():
    return AppError(409, 'RETRY_EVIDENCE_CONFLICT', '已保存的来源证据不一致，无法安全重试，请检查数据。')


def _caption_content(data_dir: Path, video_id: str) -> bytes | None:
    path = CaptionStore(data_dir.resolve()).path_for(video_id)
    if path.resolve() != path or path.is_symlink():
        raise _conflict()
    if not path.exists():
        return None
    if not path.is_file() or not 0 < path.stat().st_size <= 5 * 1024 * 1024:
        raise _conflict()
    return path.read_bytes()


def _valid_time(start, end):
    return (start is not None and end is not None and isfinite(start) and isfinite(end)
            and start >= 0 and end >= start)


def _checkpoint(session: Session, video, old_job, data_dir: Path):
    """A persisted 80% handoff proves the original Raw save transaction completed."""
    try:
        content = _caption_content(data_dir, video.id)
        cues = list(session.scalars(select(RawTranscriptCue).where(
            RawTranscriptCue.video_id == video.id).order_by(RawTranscriptCue.sequence_index)))
        words = list(session.scalars(select(RawTranscriptWord).where(
            RawTranscriptWord.video_id == video.id).order_by(RawTranscriptWord.sequence_index)))
        source = video.subtitle_source
        caption_source = source in (SubtitleSource.YOUTUBE_MANUAL, SubtitleSource.YOUTUBE_AUTO)
        if cues:
            if (old_job.progress != 80 or source is None or not video.subtitle_language
                    or [c.sequence_index for c in cues] != list(range(len(cues)))
                    or any(c.source_type != source or not _valid_time(c.start_seconds, c.end_seconds) for c in cues)
                    or not any(c.text.strip() for c in cues)):
                raise _conflict()
            cue_ids = {c.id for c in cues}
            if (words and source != SubtitleSource.STT
                    or [w.sequence_index for w in words] != list(range(len(words)))
                    or any(w.cue_id not in cue_ids or not w.text.strip() for w in words)):
                raise _conflict()
            for word in words:
                if any(t is not None and (not isfinite(t) or t < 0) for t in (word.start_seconds, word.end_seconds)):
                    raise _conflict()
                if (word.start_seconds is not None and word.end_seconds is not None
                        and word.end_seconds < word.start_seconds):
                    raise _conflict()
                if word.confidence is not None and (not isfinite(word.confidence) or not 0 <= word.confidence <= 1):
                    raise _conflict()
            if caption_source and content is not None:
                parsed = parse_vtt(content)
                if [(c.sequence_index, c.start_seconds, c.end_seconds, c.text, c.source_payload) for c in cues] != [
                        (c.sequence_index, c.start_seconds, c.end_seconds, c.text, c.source_payload) for c in parsed]:
                    raise _conflict()
            if source == SubtitleSource.STT and content is not None:
                raise _conflict()
            return ProcessingStage.NORMALIZING, 80
        if words or old_job.progress == 80:
            raise _conflict()
        if caption_source:
            if content is None or old_job.progress != 35 or not video.subtitle_language:
                raise _conflict()
            parse_vtt(content)
            return ProcessingStage.FETCHING_CAPTIONS, 35
        if content is not None:
            raise _conflict()
        if source == SubtitleSource.STT:
            if old_job.progress not in (20, 40):
                raise _conflict()
            return ProcessingStage.DOWNLOADING_AUDIO, 20
        if source is not None or video.subtitle_language is not None or old_job.progress not in (0, 10, 20, 40):
            raise _conflict()
        return ProcessingStage.FETCHING_METADATA, 0
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise _conflict() from error


def _new_retry(session: Session, video_id: str, expected_job_id: str | None, data_dir: Path):
    repository = VideoRepository(session)
    video = repository.get(video_id)
    if video is None:
        raise AppError(404, 'VIDEO_NOT_FOUND', '找不到这个视频。')
    old_job = repository.get_latest_job(video_id)
    if (old_job is None or old_job.id != expected_job_id or old_job.status != JobStatus.FAILED
            or video.status != VideoStatus.FAILED
            or session.scalar(select(ProcessingJob.id).where(
                ProcessingJob.video_id == video_id,
                ProcessingJob.status.in_((JobStatus.PENDING, JobStatus.RUNNING))).limit(1))):
        raise AppError(409, 'VIDEO_RETRY_CONFLICT', '任务状态已变化，请刷新后仅重试失败视频。')
    if video.current_revision_id is not None or any(session.scalar(select(model.id).where(
            model.video_id == video_id).limit(1)) for model in (
            LearningTranscriptSegment, TranscriptRevision, TranscriptNormalizationRun)):
        raise _conflict()
    stage, progress = _checkpoint(session, video, old_job, data_dir)
    try:
        AudioStore(data_dir).cleanup(video_id)
    except (OSError, ValueError) as error:
        raise AppError(409, 'RETRY_EVIDENCE_CONFLICT', '临时音频无法安全清理，请检查数据目录后重试。') from error
    job = ProcessingJob(video_id=video_id, stage=stage, progress=progress,
                        created_at=max(datetime.now(UTC), old_job.created_at + timedelta(microseconds=1)))
    session.add(job)
    video.status = VideoStatus.PROCESSING
    session.flush()
    return RetryVideoResponse(video_id=video_id, previous_job_id=old_job.id,
                              job=ProcessingJobResponse.model_validate(job))


def _digest(payload):
    return hashlib.sha256(json.dumps(payload.model_dump(mode='json', exclude={'idempotency_key'}),
                                     sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _replay(session, kind, target_id, payload):
    record = session.scalar(select(VideoImportRetryRequest).where(
        VideoImportRetryRequest.target_kind == kind,
        VideoImportRetryRequest.target_id == target_id,
        VideoImportRetryRequest.idempotency_key == payload.idempotency_key))
    if record and record.request_digest != _digest(payload):
        raise AppError(409, 'IDEMPOTENCY_CONFLICT', '此重试标识已用于另一份请求，请重新确认。')
    return record


def _save_request(session, kind, target_id, payload, result):
    session.add(VideoImportRetryRequest(target_kind=kind, target_id=target_id,
                idempotency_key=payload.idempotency_key, request_digest=_digest(payload),
                response_payload=result.model_dump(mode='json')))


def retry_video(session: Session, video_id: str, payload: RetryVideoRequest, data_dir: Path):
    with session.begin():
        acquire_import_write_lock(session)
        replay = _replay(session, 'video', video_id, payload)
        if replay:
            return RetryVideoResponse.model_validate(replay.response_payload), True
        result = _new_retry(session, video_id, payload.expected_job_id, data_dir)
        _save_request(session, 'video', video_id, payload, result)
    return result, False


def retry_batch(session: Session, batch_id: str, payload: RetryBatchRequest, data_dir: Path):
    with session.begin():
        acquire_import_write_lock(session)
        replay = _replay(session, 'batch', batch_id, payload)
        if replay:
            return RetryBatchResponse.model_validate(replay.response_payload), True
        if session.get(VideoImportBatch, batch_id) is None:
            raise AppError(404, 'IMPORT_BATCH_NOT_FOUND', '找不到这次导入。')
        items = {i.id: i for i in session.scalars(select(VideoImportBatchItem).where(
            VideoImportBatchItem.batch_id == batch_id))}
        if any(item_id not in items for item_id in payload.item_ids):
            raise AppError(422, 'IMPORT_SELECTION_INVALID', '请选择本批次中的导入条目。')
        results = []
        for item_id in payload.item_ids:
            item = items[item_id]
            expected = payload.expected_job_ids[item_id]
            result = RetryBatchItemResponse(item_id=item_id, video_id=item.video_id,
                                            previous_job_id=expected, status='skipped')
            if item.disposition == 'unavailable' or not item.video_id:
                result.error = PreviewError(code='VIDEO_UNAVAILABLE', message='此条目不可导入，未创建重试任务。')
            else:
                binding = session.get(VideoImportRetryBinding, item_id)
                bound_job_id = binding.job_id if binding else item.job_id if item.disposition == 'created' else None
                try:
                    # A historical created/retried batch cannot retry a different attempt silently.
                    if bound_job_id is not None and bound_job_id != expected:
                        raise AppError(409, 'VIDEO_RETRY_CONFLICT', '批次绑定任务已变化，请刷新后重试。')
                    with session.begin_nested():
                        retried = _new_retry(session, item.video_id, expected, data_dir)
                        if binding is None:
                            binding = VideoImportRetryBinding(batch_item_id=item_id, job_id=retried.job.id)
                            session.add(binding)
                        else:
                            binding.job_id = retried.job.id
                        session.flush()
                    result.status = 'accepted'
                    result.job = retried.job
                except AppError as error:
                    result.status = 'rejected'
                    result.error = PreviewError(code=error.code, message=error.message)
                    latest = VideoRepository(session).get_latest_job(item.video_id)
                    if latest and latest.id == expected and latest.status != JobStatus.FAILED:
                        result.status = 'skipped'
            results.append(result)
        response = RetryBatchResponse(batch_id=batch_id, items=results)
        _save_request(session, 'batch', batch_id, payload, response)
    return response, False

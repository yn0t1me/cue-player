from datetime import UTC, datetime, timedelta
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import ProcessingJob, VideoCollection, VideoImportPreview, VideoImportBatch, VideoImportBatchItem, VideoImportRetryBinding
from app.repositories.videos import VideoRepository
from app.schemas.video_collections import (
    BatchCounts, BatchItemResponse, BatchRequest, BatchResponse, PreviewError, PreviewItem,
    PreviewRequest, PreviewResponse, PreviewSource,
)
from app.schemas.videos import ProcessingJobResponse
from app.services.video_collections import (
    acquire_import_write_lock, append_members, collection_items, require_collection,
)
from app.services.videos import save_new_video, video_response
from app.services.youtube.parser import extract_video_id
from app.services.youtube.playlists import PlaylistSnapshot


def make_preview(session: Session, payload: PreviewRequest, snapshot: PlaylistSnapshot | None = None):
    """Persist a read-only discovery snapshot, without any videos or jobs."""
    source = PreviewSource(input_kind=payload.input_kind)
    raw_items = []
    if snapshot is not None:
        source.playlist_id = snapshot.playlist_id
        source.url = snapshot.url
        source.title = snapshot.title
        for entry in snapshot.entries:
            raw_items.append(dict(youtube_video_id=entry.video_id, title=entry.title,
                                  duration=entry.duration, thumbnail_url=entry.thumbnail_url,
                                  selectable=not entry.unavailable and entry.video_id is not None,
                                  error=PreviewError(code='VIDEO_UNAVAILABLE', message='此列表条目不可导入。')
                                  if entry.unavailable or entry.video_id is None else None))
    else:
        for url in payload.urls:
            try:
                video_id = extract_video_id(url)
                raw_items.append(dict(youtube_video_id=video_id, selectable=True))
            except ValueError:
                raw_items.append(dict(youtube_video_id=None, selectable=False,
                                      error=PreviewError(code='INVALID_YOUTUBE_URL',
                                                         message='请输入单个有效的视频链接；列表请使用播放列表入口。')))
    if len(raw_items) > 200:
        raise AppError(422, 'IMPORT_LIMIT_EXCEEDED', '每次最多预览200条，请选择较小的播放列表。')
    items = []
    seen = set()
    duplicate_count = 0
    repository = VideoRepository(session)
    for position, raw in enumerate(raw_items):
        video_id = raw['youtube_video_id']
        if video_id is not None and video_id in seen:
            duplicate_count += 1
            continue
        if video_id is not None:
            seen.add(video_id)
        existing = repository.get_by_youtube_id(video_id) if video_id else None
        item = PreviewItem(id=str(uuid4()), source_position=position,
                           url=f'https://www.youtube.com/watch?v={video_id}' if video_id else None,
                           existing_video_id=existing.id if existing else None, **raw)
        if existing:
            item.title = existing.title or item.title
            item.duration = existing.duration_seconds if existing.duration_seconds is not None else item.duration
            item.thumbnail_url = existing.thumbnail_url or item.thumbnail_url
        items.append(item)
    # Close the discovery read before writing, so concurrent previews don't upgrade read locks.
    session.rollback()
    with session.begin():
        preview = VideoImportPreview(input_kind=payload.input_kind, source=source.model_dump(),
                                     items=[i.model_dump(mode='json') for i in items],
                                     duplicate_count=duplicate_count,
                                     expires_at=datetime.now(UTC) + timedelta(minutes=30))
        session.add(preview)
        session.flush()
        result = PreviewResponse(id=preview.id, expires_at=preview.expires_at, source=source,
                                 items=items, duplicate_count=duplicate_count)
    return result


def _request_digest(payload: BatchRequest):
    body = payload.model_dump(mode='json', exclude={'idempotency_key'})
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def get_batch(session: Session, batch_id: str) -> BatchResponse:
    batch = session.get(VideoImportBatch, batch_id)
    if batch is None:
        raise AppError(404, 'IMPORT_BATCH_NOT_FOUND', '找不到这次导入。')
    repository = VideoRepository(session)
    counts = BatchCounts()
    items = []
    for item in session.scalars(select(VideoImportBatchItem).where(
            VideoImportBatchItem.batch_id == batch.id).order_by(VideoImportBatchItem.position)):
        video = repository.get(item.video_id) if item.video_id else None
        current_job = repository.get_latest_job(video.id) if video else None
        binding = session.get(VideoImportRetryBinding, item.id)
        job = (session.get(ProcessingJob, binding.job_id) if binding else
               session.get(ProcessingJob, item.job_id) if item.disposition == 'created' and item.job_id else current_job)
        counts.total += 1
        if item.disposition == 'unavailable':
            counts.unavailable += 1
        elif job and job.status == 'pending':
            counts.waiting += 1
        elif job and job.status == 'running':
            counts.running += 1
        elif job and job.status == 'failed':
            counts.failed += 1
        elif video and ((job is None and video.status == 'ready') or (job and job.status == 'completed')):
            counts.ready += 1
        else:
            # Inconsistent legacy state must not be represented as successful import.
            counts.failed += 1
        items.append(BatchItemResponse(
            id=item.id, preview_item_id=item.preview_item_id, position=item.position,
            youtube_video_id=item.youtube_video_id, disposition=item.disposition,
            video=video_response(video, current_job) if video else None,
            job=ProcessingJobResponse.model_validate(job) if job else None,
            error=PreviewError(code=item.error_code, message=item.error_message)
            if item.error_code else None))
    status = ('running' if counts.running else 'pending' if counts.waiting
              else 'completed_with_errors' if counts.failed or counts.unavailable else 'completed')
    return BatchResponse(id=batch.id, preview_id=batch.preview_id, collection_id=batch.collection_id,
                         collection_name_snapshot=batch.collection_name_snapshot,
                         subtitle_preference=batch.subtitle_preference, created_at=batch.created_at,
                         status=status, counts=counts, items=items)


def submit_batch(session: Session, payload: BatchRequest) -> tuple[BatchResponse, bool]:
    digest = _request_digest(payload)
    with session.begin():
        acquire_import_write_lock(session)
        existing = session.scalar(select(VideoImportBatch).where(
            VideoImportBatch.idempotency_key == payload.idempotency_key))
        if existing:
            if existing.request_digest != digest:
                raise AppError(409, 'IDEMPOTENCY_CONFLICT', '此提交标识已用于另一份导入，请重新确认。')
            return get_batch(session, existing.id), True
        preview = session.get(VideoImportPreview, payload.preview_id)
        if preview is None:
            raise AppError(404, 'IMPORT_PREVIEW_NOT_FOUND', '找不到导入预览，请重新获取。')
        if preview.expires_at <= datetime.now(UTC):
            raise AppError(409, 'IMPORT_PREVIEW_EXPIRED', '导入预览已过期，请重新获取。')
        by_id = {i['id']: PreviewItem.model_validate(i) for i in preview.items}
        selected = payload.selected_item_ids
        if len(set(selected)) != len(selected) or any(i not in by_id or not by_id[i].selectable for i in selected):
            raise AppError(422, 'IMPORT_SELECTION_INVALID', '请选择本次预览中不重复的可导入视频。')
        collection = None
        if payload.target.kind == 'existing':
            collection = require_collection(session, payload.target.collection_id)
        elif payload.target.kind == 'new':
            collection = VideoCollection(name=payload.target.name, description=payload.target.description,
                                         source_playlist_id=preview.source.get('playlist_id'),
                                         source_playlist_url=preview.source.get('url'))
            session.add(collection)
            session.flush()
        known_members = {m.video_id for m in collection_items(session, collection.id)} if collection else set()
        batch = VideoImportBatch(preview_id=preview.id, idempotency_key=payload.idempotency_key,
                                 request_digest=digest, subtitle_preference=payload.subtitle_preference.value,
                                 collection_id=collection.id if collection else None,
                                 collection_name_snapshot=collection.name if collection else None)
        session.add(batch)
        session.flush()
        repository = VideoRepository(session)
        member_video_ids = []
        pending_items = [by_id[i] for i in selected] + [i for i in by_id.values() if not i.selectable]
        for position, item in enumerate(pending_items):
            video = None
            job = None
            disposition = 'unavailable'
            if item.selectable:
                video = repository.get_by_youtube_id(item.youtube_video_id)
                if video is None:
                    video, job = save_new_video(session, item.youtube_video_id, payload.subtitle_preference)
                    disposition = 'created'
                else:
                    job = repository.get_latest_job(video.id)
                    disposition = 'already_member' if video.id in known_members else 'reused'
                member_video_ids.append(video.id)
            session.add(VideoImportBatchItem(
                batch_id=batch.id, preview_item_id=item.id, position=position,
                youtube_video_id=item.youtube_video_id, video_id=video.id if video else None,
                job_id=job.id if job else None, disposition=disposition,
                error_code=item.error.code if item.error else None,
                error_message=item.error.message if item.error else None))
        if collection:
            append_members(session, collection, member_video_ids)
        session.flush()
        result = get_batch(session, batch.id)
    return result, False

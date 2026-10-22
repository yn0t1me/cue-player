from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import VideoStatus
from app.core.errors import AppError
from app.db.models import LearningTranscriptSegment, TranscriptRevision, Video
from app.schemas.transcripts import TranscriptResponse, TranscriptSegmentResponse


def get_transcript(session: Session, video_id: str) -> TranscriptResponse:
    video = session.get(Video, video_id)
    if video is None:
        raise AppError(404, 'VIDEO_NOT_FOUND', '找不到这个视频，请返回视频库。')
    if video.status == VideoStatus.PROCESSING:
        raise AppError(409, 'TRANSCRIPT_NOT_READY', '学习字幕仍在准备中，请稍后再试。')
    if video.status == VideoStatus.FAILED:
        raise AppError(409, 'TRANSCRIPT_UNAVAILABLE', '这个视频的字幕处理未成功。')
    revision = session.get(TranscriptRevision, video.current_revision_id) if video.current_revision_id else None
    if revision is None or revision.video_id != video_id:
        raise AppError(409, 'TRANSCRIPT_UNAVAILABLE', '这个视频没有可读取的学习字幕。')
    return _revision_transcript(session, video_id, revision)


def _revision_transcript(session: Session, video_id: str,
                         revision: TranscriptRevision) -> TranscriptResponse:
    rows = session.scalars(
        select(LearningTranscriptSegment)
        .where(LearningTranscriptSegment.revision_id == revision.id)
        .order_by(LearningTranscriptSegment.sequence_index)).all()
    if not rows:
        raise AppError(409, 'TRANSCRIPT_UNAVAILABLE', '这个视频没有可读取的学习字幕。')
    versions = {row.normalization_version for row in rows}
    if len(versions) != 1:
        raise RuntimeError('Learning transcript contains mixed normalization versions')
    return TranscriptResponse(
        video_id=video_id,
        revision_id=revision.id,
        origin=revision.origin,
        normalization_version=versions.pop(),
        segments=[TranscriptSegmentResponse(
            id=row.id,
            sequence_index=row.sequence_index,
            start=row.start_seconds,
            end=row.end_seconds,
            text=row.text,
            translation_zh=row.translation_zh,
        ) for row in rows],
    )


def get_transcript_revision(session: Session, video_id: str,
                            revision_id: str) -> TranscriptResponse:
    get_transcript(session, video_id)
    revision = session.get(TranscriptRevision, revision_id)
    if revision is None or revision.video_id != video_id:
        raise AppError(404, 'TRANSCRIPT_REVISION_NOT_FOUND', '找不到这份字幕版本。')
    return _revision_transcript(session, video_id, revision)


def list_transcript_revisions(session: Session, video_id: str) -> dict:
    current = get_transcript(session, video_id)
    rows = session.scalars(select(TranscriptRevision).where(
        TranscriptRevision.video_id == video_id)
        .order_by(TranscriptRevision.revision_number.desc())).all()
    items = []
    for revision in rows:
        count, version = session.execute(select(
            func.count(LearningTranscriptSegment.id),
            func.min(LearningTranscriptSegment.normalization_version),
        ).where(LearningTranscriptSegment.revision_id == revision.id)).one()
        items.append({'id': revision.id, 'origin': revision.origin,
                      'revision_number': revision.revision_number,
                      'created_at': revision.created_at,
                      'normalization_version': version, 'segment_count': count,
                      'is_current': revision.id == current.revision_id})
    return {'items': items}

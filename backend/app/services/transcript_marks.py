from sqlalchemy import case, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import VideoStatus
from app.core.errors import AppError
from app.db.models import (
    LearningTranscriptSegment, TranscriptMark, TranscriptMarkKey, TranscriptRevision, Video,
)
from app.schemas.transcript_marks import (
    CreateTranscriptMarkRequest, TranscriptMarkListResponse,
    TranscriptMarkResponse, TranscriptSelectionRequest,
)


def _ready_video(session: Session, video_id: str) -> Video:
    video = session.get(Video, video_id)
    if video is None:
        raise AppError(404, 'VIDEO_NOT_FOUND', '找不到这个视频，请返回视频库。')
    if video.status != VideoStatus.READY or video.current_revision_id is None:
        raise AppError(409, 'TRANSCRIPT_UNAVAILABLE', '这个视频尚无可标记的阅读字幕。')
    return video


def _response(mark: TranscriptMark, segment: LearningTranscriptSegment,
              revision: TranscriptRevision, current_revision_id: str) -> TranscriptMarkResponse:
    return TranscriptMarkResponse(
        id=mark.id, video_id=mark.video_id,
        revision_id=mark.revision_id, revision_number=revision.revision_number,
        revision_origin=revision.origin, is_current=revision.id == current_revision_id,
        segment_id=mark.segment_id, segment_sequence_index=segment.sequence_index,
        segment_start=segment.start_seconds, segment_end=segment.end_seconds,
        segment_text=segment.text, start_offset=mark.start_offset,
        end_offset=mark.end_offset, selected_text=mark.selected_text,
        created_at=mark.created_at, updated_at=mark.updated_at,
    )


def _mark_with_context(session: Session, video_id: str, mark_id: str):
    row = session.execute(
        select(TranscriptMark, LearningTranscriptSegment, TranscriptRevision)
        .join(LearningTranscriptSegment,
              TranscriptMark.segment_id == LearningTranscriptSegment.id)
        .join(TranscriptRevision, TranscriptMark.revision_id == TranscriptRevision.id)
        .where(TranscriptMark.id == mark_id, TranscriptMark.video_id == video_id)
    ).one_or_none()
    if row is None:
        raise AppError(404, 'TRANSCRIPT_MARK_NOT_FOUND', '找不到这条字幕标记。')
    return row


def list_marks(session: Session, video_id: str) -> TranscriptMarkListResponse:
    video = _ready_video(session, video_id)
    rows = session.execute(
        select(TranscriptMark, LearningTranscriptSegment, TranscriptRevision)
        .join(LearningTranscriptSegment,
              TranscriptMark.segment_id == LearningTranscriptSegment.id)
        .join(TranscriptRevision, TranscriptMark.revision_id == TranscriptRevision.id)
        .where(TranscriptMark.video_id == video_id)
        .order_by(
            case((TranscriptRevision.id == video.current_revision_id, 0), else_=1),
            TranscriptRevision.revision_number.desc(),
            LearningTranscriptSegment.start_seconds,
            LearningTranscriptSegment.sequence_index,
            TranscriptMark.start_offset,
            TranscriptMark.created_at,
            TranscriptMark.id,
        )
    ).all()
    return TranscriptMarkListResponse(items=[
        _response(mark, segment, revision, video.current_revision_id)
        for mark, segment, revision in rows
    ])


def lock_video(session: Session, video_id: str) -> None:
    # Acquire the SQLite write lock before any reads; also serializes publication/deletion.
    locked = session.execute(text(
        'UPDATE videos SET current_revision_id = current_revision_id WHERE id = :id'),
        {'id': video_id})
    if locked.rowcount != 1:
        raise AppError(404, 'VIDEO_NOT_FOUND', '找不到这个视频，请返回视频库。')


def validate_selection(
        session: Session, video: Video, payload: TranscriptSelectionRequest,
) -> tuple[TranscriptRevision, LearningTranscriptSegment]:
    video_id = video.id
    if video.current_revision_id != payload.revision_id:
        raise AppError(409, 'TRANSCRIPT_REVISION_CONFLICT',
                       '当前字幕已变化，请刷新后重新选择要标记的文字。')
    revision = session.get(TranscriptRevision, payload.revision_id)
    segment = session.get(LearningTranscriptSegment, payload.segment_id)
    if (revision is None or revision.video_id != video_id or segment is None
            or segment.video_id != video_id or segment.revision_id != revision.id):
        raise AppError(404, 'TRANSCRIPT_SEGMENT_NOT_FOUND', '找不到这条当前字幕。')
    if (payload.start_offset >= payload.end_offset
            or payload.end_offset > len(segment.text)
            or segment.text[payload.start_offset:payload.end_offset] != payload.selected_text
            or not payload.selected_text.strip()):
        raise AppError(422, 'MARK_SELECTION_INVALID',
                       '标记范围与当前字幕不一致，请重新选择。')
    return revision, segment


def create_mark(session_factory: sessionmaker[Session], video_id: str,
                payload: CreateTranscriptMarkRequest) -> tuple[TranscriptMarkResponse, bool]:
    with session_factory() as session:
        lock_video(session, video_id)
        video = _ready_video(session, video_id)
        revision, segment = validate_selection(session, video, payload)
        mark, created = get_or_create_mark(session, video_id, payload)
        session.commit()
        return _response(mark, segment, revision, video.current_revision_id), created


def get_or_create_mark(session: Session, video_id: str,
                       payload: CreateTranscriptMarkRequest) -> tuple[TranscriptMark, bool]:
    """Persist a validated selection inside the caller's locked transaction."""
    key_id = (video_id, payload.revision_id, payload.segment_id,
              payload.start_offset, payload.end_offset)
    key = session.get(TranscriptMarkKey, key_id)
    if key is not None:
        return session.get(TranscriptMark, key.mark_id), False
    values = payload.model_dump()
    mark = TranscriptMark(video_id=video_id, **values)
    session.add(mark)
    session.flush()
    session.add(TranscriptMarkKey(
        video_id=video_id, revision_id=payload.revision_id, segment_id=payload.segment_id,
        start_offset=payload.start_offset, end_offset=payload.end_offset, mark_id=mark.id))
    return mark, True


def delete_mark(session: Session, video_id: str, mark_id: str) -> None:
    lock_video(session, video_id)
    _ready_video(session, video_id)
    mark, _, _ = _mark_with_context(session, video_id, mark_id)
    key_id = (mark.video_id, mark.revision_id, mark.segment_id,
              mark.start_offset, mark.end_offset)
    key = session.get(TranscriptMarkKey, key_id)
    if key is not None and key.mark_id == mark.id:
        candidates = session.scalars(select(TranscriptMark).where(
            TranscriptMark.video_id == mark.video_id,
            TranscriptMark.revision_id == mark.revision_id,
            TranscriptMark.segment_id == mark.segment_id,
            TranscriptMark.start_offset == mark.start_offset,
            TranscriptMark.end_offset == mark.end_offset,
            TranscriptMark.id != mark.id)).all()
        if candidates:
            chosen = min(candidates, key=lambda item: (
                item.created_at, item.id))
            key.mark_id = chosen.id
        else:
            session.delete(key)
        session.flush()
    session.delete(mark)
    session.commit()

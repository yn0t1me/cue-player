from sqlalchemy import case, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.db.models import LearningTranscriptSegment, TranscriptQuestion, TranscriptRevision
from app.schemas.transcript_questions import (
    CreateTranscriptQuestionRequest, UpdateTranscriptQuestionRequest,
    TranscriptQuestionResponse, TranscriptQuestionListResponse,
)
from app.schemas.transcript_marks import CreateTranscriptMarkRequest
from app.services.transcript_marks import (
    _ready_video, get_or_create_mark, lock_video, validate_selection,
)


def _response(item, segment, revision, current_revision_id):
    return TranscriptQuestionResponse(
        id=item.id, video_id=item.video_id,
        revision_id=item.revision_id, revision_number=revision.revision_number,
        revision_origin=revision.origin, is_current=revision.id == current_revision_id,
        segment_id=item.segment_id, segment_sequence_index=segment.sequence_index,
        segment_start=segment.start_seconds, segment_end=segment.end_seconds,
        segment_text=segment.text, start_offset=item.start_offset,
        end_offset=item.end_offset, selected_text=item.selected_text,
        question=item.question, answer=item.answer,
        created_at=item.created_at, updated_at=item.updated_at,
    )


def _context_query():
    return (select(TranscriptQuestion, LearningTranscriptSegment, TranscriptRevision)
            .join(LearningTranscriptSegment,
                  TranscriptQuestion.segment_id == LearningTranscriptSegment.id)
            .join(TranscriptRevision, TranscriptQuestion.revision_id == TranscriptRevision.id))


def _with_context(session, video_id, question_id):
    row = session.execute(_context_query().where(
        TranscriptQuestion.video_id == video_id,
        TranscriptQuestion.id == question_id)).one_or_none()
    if row is None:
        raise AppError(404, 'TRANSCRIPT_QUESTION_NOT_FOUND', '找不到这条字幕提问。')
    return row


def list_questions(session: Session, video_id: str) -> TranscriptQuestionListResponse:
    video = _ready_video(session, video_id)
    rows = session.execute(_context_query().where(
        TranscriptQuestion.video_id == video_id).order_by(
            case((TranscriptRevision.id == video.current_revision_id, 0), else_=1),
            TranscriptRevision.revision_number.desc(),
            LearningTranscriptSegment.start_seconds,
            LearningTranscriptSegment.sequence_index,
            TranscriptQuestion.start_offset, TranscriptQuestion.created_at,
            TranscriptQuestion.id)).all()
    return TranscriptQuestionListResponse(items=[
        _response(item, segment, revision, video.current_revision_id)
        for item, segment, revision in rows])


def _collect_first_answer(session: Session, item: TranscriptQuestion) -> None:
    if not (item.answer and item.answer.strip()) or item.has_saved_answer:
        return
    anchor = CreateTranscriptMarkRequest.model_validate(item, from_attributes=True)
    get_or_create_mark(session, item.video_id, anchor)
    item.has_saved_answer = True


def create_question(session_factory: sessionmaker[Session], video_id: str,
                    payload: CreateTranscriptQuestionRequest) -> TranscriptQuestionResponse:
    with session_factory() as session:
        lock_video(session, video_id)
        video = _ready_video(session, video_id)
        revision, segment = validate_selection(session, video, payload)
        item = TranscriptQuestion(video_id=video_id, **payload.model_dump())
        session.add(item)
        _collect_first_answer(session, item)
        session.commit()
        return _response(item, segment, revision, video.current_revision_id)


def update_question(session: Session, video_id: str, question_id: str,
                    payload: UpdateTranscriptQuestionRequest) -> TranscriptQuestionResponse:
    lock_video(session, video_id)
    video = _ready_video(session, video_id)
    item, segment, revision = _with_context(session, video_id, question_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    _collect_first_answer(session, item)
    session.commit()
    return _response(item, segment, revision, video.current_revision_id)


def delete_question(session: Session, video_id: str, question_id: str) -> None:
    lock_video(session, video_id)
    _ready_video(session, video_id)
    item, _, _ = _with_context(session, video_id, question_id)
    session.delete(item)
    session.commit()

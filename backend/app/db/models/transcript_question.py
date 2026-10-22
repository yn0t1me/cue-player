from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityCreated, Updated


class TranscriptQuestion(IdentityCreated, Updated, Base):
    __tablename__ = 'transcript_questions'
    __table_args__ = (
        CheckConstraint('start_offset >= 0', name='ck_transcript_questions_start_offset'),
        CheckConstraint('end_offset > start_offset', name='ck_transcript_questions_end_offset'),
        CheckConstraint('length(trim(selected_text)) > 0',
                        name='ck_transcript_questions_selected_text'),
        CheckConstraint('length(trim(question)) > 0 AND length(question) <= 10000',
                        name='ck_transcript_questions_question'),
        CheckConstraint('answer IS NULL OR length(answer) <= 100000',
                        name='ck_transcript_questions_answer'),
    )

    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('transcript_revisions.id', ondelete='RESTRICT'), index=True)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('learning_transcript_segments.id', ondelete='RESTRICT'), index=True)
    start_offset: Mapped[int]
    end_offset: Mapped[int]
    selected_text: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)

    # A durable event marker, independent of the current answer and favorite.
    has_saved_answer: Mapped[bool] = mapped_column(Boolean(), default=False, server_default=false())

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityCreated, Updated


class TranscriptMark(IdentityCreated, Updated, Base):
    __tablename__ = 'transcript_marks'
    __table_args__ = (
        CheckConstraint('start_offset >= 0', name='ck_transcript_marks_start_offset'),
        CheckConstraint('end_offset > start_offset', name='ck_transcript_marks_end_offset'),
        CheckConstraint('length(trim(selected_text)) > 0',
                        name='ck_transcript_marks_selected_text'),
    )

    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('transcript_revisions.id', ondelete='RESTRICT'), index=True)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('learning_transcript_segments.id', ondelete='RESTRICT'),
        index=True)
    start_offset: Mapped[int]
    end_offset: Mapped[int]
    selected_text: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

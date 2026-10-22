from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TranscriptMarkKey(Base):
    """One canonical favorite per selection, preserving historical duplicate rows."""
    __tablename__ = 'transcript_mark_keys'

    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('videos.id', ondelete='RESTRICT'), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('transcript_revisions.id', ondelete='RESTRICT'), primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('learning_transcript_segments.id', ondelete='RESTRICT'), primary_key=True)
    start_offset: Mapped[int] = mapped_column(primary_key=True)
    end_offset: Mapped[int] = mapped_column(primary_key=True)
    mark_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('transcript_marks.id', ondelete='RESTRICT'), unique=True)

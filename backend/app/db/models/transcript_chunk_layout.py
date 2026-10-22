from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityCreated, Updated


class TranscriptChunkLayout(IdentityCreated, Updated, Base):
    __tablename__ = 'transcript_chunk_layouts'
    __table_args__ = (
        UniqueConstraint('revision_id', name='uq_transcript_chunk_layouts_revision'),
        CheckConstraint('length(content_sha256) = 64',
                        name='ck_transcript_chunk_layouts_digest'),
    )

    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('transcript_revisions.id', ondelete='RESTRICT'), index=True)
    content_sha256: Mapped[str] = mapped_column(String(64))


class TranscriptChunkSegment(IdentityCreated, Base):
    __tablename__ = 'transcript_chunk_segments'
    __table_args__ = (
        UniqueConstraint('layout_id', 'segment_id',
                         name='uq_transcript_chunk_segments_layout_segment'),
    )

    layout_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('transcript_chunk_layouts.id', ondelete='CASCADE'),
        index=True)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey('learning_transcript_segments.id', ondelete='RESTRICT'),
        index=True)
    boundary_offsets: Mapped[list[int]] = mapped_column(JSON(none_as_null=True))

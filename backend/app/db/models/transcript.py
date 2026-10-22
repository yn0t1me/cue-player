from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SubtitleSource
from app.db.base import Base, IdentityCreated, Updated, enum_column


def sequence_constraints(table: str):
    return (
        UniqueConstraint('video_id', 'sequence_index', name=f'uq_{table}_video_sequence'),
        CheckConstraint('sequence_index >= 0', name=f'ck_{table}_sequence'),
    )


class RawTranscriptCue(IdentityCreated, Base):
    __tablename__ = 'raw_transcript_cues'
    __table_args__ = sequence_constraints(__tablename__)

    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    sequence_index: Mapped[int]
    start_seconds: Mapped[float]
    end_seconds: Mapped[float]
    text: Mapped[str] = mapped_column(Text)
    source_type: Mapped[SubtitleSource] = mapped_column(enum_column(SubtitleSource, 'cue_source_type'))
    source_payload: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))


class RawTranscriptWord(IdentityCreated, Base):
    __tablename__ = 'raw_transcript_words'
    __table_args__ = sequence_constraints(__tablename__)

    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    cue_id: Mapped[str | None] = mapped_column(ForeignKey('raw_transcript_cues.id', ondelete='RESTRICT'), index=True)
    sequence_index: Mapped[int]
    text: Mapped[str]
    start_seconds: Mapped[float | None]
    end_seconds: Mapped[float | None]
    confidence: Mapped[float | None]


class TranscriptRevision(IdentityCreated, Base):
    __tablename__ = 'transcript_revisions'
    __table_args__ = (
        CheckConstraint("origin IN ('generated', 'source_aligned')",
                        name='ck_transcript_revisions_origin'),
        CheckConstraint('revision_number >= 1', name='ck_transcript_revisions_number'),
        UniqueConstraint('video_id', 'revision_number',
                         name='uq_transcript_revisions_video_number'),
    )

    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    origin: Mapped[str]
    revision_number: Mapped[int]
    content_sha256: Mapped[str | None] = mapped_column(String(64))


class LearningTranscriptSegment(IdentityCreated, Updated, Base):
    __tablename__ = 'learning_transcript_segments'
    __table_args__ = (
        UniqueConstraint('revision_id', 'sequence_index',
                         name='uq_learning_transcript_segments_revision_sequence'),
        CheckConstraint('sequence_index >= 0', name='ck_learning_transcript_segments_sequence'),
        CheckConstraint(
            "(normalization_version IS NOT NULL AND normalization_version = 2 AND source_ref_type = 'cue') OR "
            "(normalization_version IS NULL AND source_ref_type = 'source_units')",
            name='ck_learning_transcript_segments_version'),
    )

    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey('transcript_revisions.id', ondelete='RESTRICT'), index=True)
    sequence_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    translation_zh: Mapped[str | None] = mapped_column(Text)
    start_seconds: Mapped[float]
    end_seconds: Mapped[float]
    source_ref_type: Mapped[str]
    source_refs: Mapped[dict] = mapped_column(JSON(none_as_null=True))
    normalization_version: Mapped[int | None] = mapped_column(server_default='2')
    normalization_run_id: Mapped[str | None] = mapped_column(
        ForeignKey('transcript_normalization_runs.id', ondelete='RESTRICT'), index=True)


class TranscriptNormalizationRun(IdentityCreated, Base):
    __tablename__ = 'transcript_normalization_runs'
    __table_args__ = (
        CheckConstraint("method = 'deterministic'", name='ck_transcript_normalization_runs_method'),
        CheckConstraint('normalization_version = 2', name='ck_transcript_normalization_runs_version'),
        CheckConstraint('input_unit_count > 0', name='ck_transcript_normalization_runs_units'),
    )

    video_id: Mapped[str] = mapped_column(
        ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey('processing_jobs.id', ondelete='RESTRICT'), unique=True)
    method: Mapped[str]
    normalization_version: Mapped[int]
    input_unit_count: Mapped[int]

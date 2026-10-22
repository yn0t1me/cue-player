"""create m0 tables

Revision ID: 001_create_m0_tables
Revises:
Create Date: 2026-09-05 19:27:58.132763

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_create_m0_tables'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('videos',
    sa.Column('youtube_video_id', sa.String(length=32), nullable=False),
    sa.Column('youtube_url', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('channel_title', sa.Text(), nullable=True),
    sa.Column('duration_seconds', sa.Float(), nullable=True),
    sa.Column('thumbnail_url', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('processing', 'ready', 'failed', name='video_status', native_enum=False, create_constraint=True), server_default='processing', nullable=False),
    sa.Column('subtitle_source', sa.Enum('youtube_manual', 'youtube_auto', 'stt', name='video_subtitle_source', native_enum=False, create_constraint=True), nullable=True),
    sa.Column('subtitle_language', sa.String(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_videos'))
    )
    op.create_index(op.f('ix_videos_youtube_video_id'), 'videos', ['youtube_video_id'], unique=True)
    op.create_table('learning_transcript_segments',
    sa.Column('video_id', sa.String(length=36), nullable=False),
    sa.Column('sequence_index', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('start_seconds', sa.Float(), nullable=False),
    sa.Column('end_seconds', sa.Float(), nullable=False),
    sa.Column('source_ref_type', sa.String(), nullable=False),
    sa.Column('source_refs', sa.JSON(none_as_null=True), nullable=False),
    sa.Column('normalization_version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('normalization_version >= 1', name='ck_learning_transcript_segments_version'),
    sa.CheckConstraint('sequence_index >= 0', name='ck_learning_transcript_segments_sequence'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_learning_transcript_segments_video_id_videos'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_learning_transcript_segments')),
    sa.UniqueConstraint('video_id', 'sequence_index', name='uq_learning_transcript_segments_video_sequence')
    )
    op.create_index(op.f('ix_learning_transcript_segments_video_id'), 'learning_transcript_segments', ['video_id'], unique=False)
    op.create_table('processing_jobs',
    sa.Column('video_id', sa.String(length=36), nullable=False),
    sa.Column('stage', sa.Enum('fetching_metadata', 'fetching_captions', 'downloading_audio', 'transcribing', 'normalizing', 'completed', 'failed', name='processing_stage', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='job_status', native_enum=False, create_constraint=True), server_default='pending', nullable=False),
    sa.Column('progress', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error_code', sa.String(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('progress >= 0 AND progress <= 100', name='ck_processing_jobs_progress'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_processing_jobs_video_id_videos'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_processing_jobs'))
    )
    op.create_index(op.f('ix_processing_jobs_video_id'), 'processing_jobs', ['video_id'], unique=False)
    op.create_table('raw_transcript_cues',
    sa.Column('video_id', sa.String(length=36), nullable=False),
    sa.Column('sequence_index', sa.Integer(), nullable=False),
    sa.Column('start_seconds', sa.Float(), nullable=False),
    sa.Column('end_seconds', sa.Float(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('source_type', sa.Enum('youtube_manual', 'youtube_auto', 'stt', name='cue_source_type', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('source_payload', sa.JSON(none_as_null=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('sequence_index >= 0', name='ck_raw_transcript_cues_sequence'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_raw_transcript_cues_video_id_videos'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_raw_transcript_cues')),
    sa.UniqueConstraint('video_id', 'sequence_index', name='uq_raw_transcript_cues_video_sequence')
    )
    op.create_index(op.f('ix_raw_transcript_cues_video_id'), 'raw_transcript_cues', ['video_id'], unique=False)
    op.create_table('raw_transcript_words',
    sa.Column('video_id', sa.String(length=36), nullable=False),
    sa.Column('cue_id', sa.String(length=36), nullable=True),
    sa.Column('sequence_index', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(), nullable=False),
    sa.Column('start_seconds', sa.Float(), nullable=True),
    sa.Column('end_seconds', sa.Float(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('sequence_index >= 0', name='ck_raw_transcript_words_sequence'),
    sa.ForeignKeyConstraint(['cue_id'], ['raw_transcript_cues.id'], name=op.f('fk_raw_transcript_words_cue_id_raw_transcript_cues'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_raw_transcript_words_video_id_videos'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_raw_transcript_words')),
    sa.UniqueConstraint('video_id', 'sequence_index', name='uq_raw_transcript_words_video_sequence')
    )
    op.create_index(op.f('ix_raw_transcript_words_cue_id'), 'raw_transcript_words', ['cue_id'], unique=False)
    op.create_index(op.f('ix_raw_transcript_words_video_id'), 'raw_transcript_words', ['video_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_raw_transcript_words_video_id'), table_name='raw_transcript_words')
    op.drop_index(op.f('ix_raw_transcript_words_cue_id'), table_name='raw_transcript_words')
    op.drop_table('raw_transcript_words')
    op.drop_index(op.f('ix_raw_transcript_cues_video_id'), table_name='raw_transcript_cues')
    op.drop_table('raw_transcript_cues')
    op.drop_index(op.f('ix_processing_jobs_video_id'), table_name='processing_jobs')
    op.drop_table('processing_jobs')
    op.drop_index(op.f('ix_learning_transcript_segments_video_id'), table_name='learning_transcript_segments')
    op.drop_table('learning_transcript_segments')
    op.drop_index(op.f('ix_videos_youtube_video_id'), table_name='videos')
    op.drop_table('videos')

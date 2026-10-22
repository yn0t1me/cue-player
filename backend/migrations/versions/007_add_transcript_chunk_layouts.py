"""Add revision-anchored transcript chunk layouts.

Revision ID: 007_add_chunk_layouts
Revises: 006_add_transcript_marks
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa


revision = '007_add_chunk_layouts'
down_revision = '006_add_transcript_marks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'transcript_chunk_layouts',
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('content_sha256', sa.String(length=64), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('length(content_sha256) = 64',
                           name='ck_transcript_chunk_layouts_digest'),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'],
                                name='fk_transcript_chunk_layouts_video_id_videos',
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['revision_id'], ['transcript_revisions.id'],
                                name='fk_transcript_chunk_layouts_revision_id_transcript_revisions',
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_chunk_layouts'),
        sa.UniqueConstraint('revision_id', name='uq_transcript_chunk_layouts_revision'),
    )
    op.create_index('ix_transcript_chunk_layouts_video_id',
                    'transcript_chunk_layouts', ['video_id'])
    op.create_index('ix_transcript_chunk_layouts_revision_id',
                    'transcript_chunk_layouts', ['revision_id'])
    op.create_table(
        'transcript_chunk_segments',
        sa.Column('layout_id', sa.String(length=36), nullable=False),
        sa.Column('segment_id', sa.String(length=36), nullable=False),
        sa.Column('boundary_offsets', sa.JSON(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['layout_id'], ['transcript_chunk_layouts.id'],
                                name='fk_transcript_chunk_segments_layout_id_transcript_chunk_layouts',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['segment_id'], ['learning_transcript_segments.id'],
                                name='fk_transcript_chunk_segments_segment_id_learning_transcript_segments',
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_chunk_segments'),
        sa.UniqueConstraint('layout_id', 'segment_id',
                            name='uq_transcript_chunk_segments_layout_segment'),
    )
    op.create_index('ix_transcript_chunk_segments_layout_id',
                    'transcript_chunk_segments', ['layout_id'])
    op.create_index('ix_transcript_chunk_segments_segment_id',
                    'transcript_chunk_segments', ['segment_id'])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM transcript_chunk_layouts')):
        raise RuntimeError('Cannot downgrade while transcript chunk layouts exist')
    op.drop_index('ix_transcript_chunk_segments_segment_id',
                  table_name='transcript_chunk_segments')
    op.drop_index('ix_transcript_chunk_segments_layout_id',
                  table_name='transcript_chunk_segments')
    op.drop_table('transcript_chunk_segments')
    op.drop_index('ix_transcript_chunk_layouts_revision_id',
                  table_name='transcript_chunk_layouts')
    op.drop_index('ix_transcript_chunk_layouts_video_id',
                  table_name='transcript_chunk_layouts')
    op.drop_table('transcript_chunk_layouts')

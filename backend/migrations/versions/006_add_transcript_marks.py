"""Add version-anchored transcript marks without changing published transcripts.

Revision ID: 006_add_transcript_marks
Revises: 005_add_transcript_revisions
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = '006_add_transcript_marks'
down_revision = '005_add_transcript_revisions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'transcript_marks',
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('revision_id', sa.String(length=36), nullable=False),
        sa.Column('segment_id', sa.String(length=36), nullable=False),
        sa.Column('start_offset', sa.Integer(), nullable=False),
        sa.Column('end_offset', sa.Integer(), nullable=False),
        sa.Column('selected_text', sa.Text(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('start_offset >= 0', name='ck_transcript_marks_start_offset'),
        sa.CheckConstraint('end_offset > start_offset', name='ck_transcript_marks_end_offset'),
        sa.CheckConstraint('length(trim(selected_text)) > 0',
                           name='ck_transcript_marks_selected_text'),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'],
                                name='fk_transcript_marks_video_id_videos',
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['revision_id'], ['transcript_revisions.id'],
                                name='fk_transcript_marks_revision_id_transcript_revisions',
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['segment_id'], ['learning_transcript_segments.id'],
                                name='fk_transcript_marks_segment_id_learning_transcript_segments',
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_marks'),
    )
    op.create_index('ix_transcript_marks_video_id', 'transcript_marks', ['video_id'])
    op.create_index('ix_transcript_marks_revision_id', 'transcript_marks', ['revision_id'])
    op.create_index('ix_transcript_marks_segment_id', 'transcript_marks', ['segment_id'])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM transcript_marks')):
        raise RuntimeError('Cannot downgrade while transcript marks exist')
    op.drop_index('ix_transcript_marks_segment_id', table_name='transcript_marks')
    op.drop_index('ix_transcript_marks_revision_id', table_name='transcript_marks')
    op.drop_index('ix_transcript_marks_video_id', table_name='transcript_marks')
    op.drop_table('transcript_marks')

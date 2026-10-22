"""Remove personal notes and questions while preserving every favorite.

Revision ID: 015_retire_notes_questions
Revises: 014_retire_legacy_subtitles
"""
from importlib import import_module

from alembic import op
import sqlalchemy as sa

revision = '015_retire_notes_questions'
down_revision = '014_retire_legacy_subtitles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('transcript_questions')
    # Native DROP COLUMN avoids rebuilding marks referenced by mark_keys.
    op.drop_column('transcript_marks', 'note')


def downgrade() -> None:
    # Restore structure only. Deleted user content cannot be recovered here.
    op.add_column('transcript_marks', sa.Column('note', sa.Text(), nullable=True))
    legacy = import_module('migrations.versions.009_add_notes_experience')
    op.create_table(
        'transcript_questions', *legacy._anchor_columns(),
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('selected_text', sa.Text(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('has_saved_answer', sa.Boolean(), server_default=sa.false(), nullable=False),
        *legacy._anchor_foreign_keys('transcript_questions'),
        sa.CheckConstraint('start_offset >= 0', name='ck_transcript_questions_start_offset'),
        sa.CheckConstraint('end_offset > start_offset', name='ck_transcript_questions_end_offset'),
        sa.CheckConstraint('length(trim(selected_text)) > 0', name='ck_transcript_questions_selected_text'),
        sa.CheckConstraint('length(trim(question)) > 0 AND length(question) <= 10000', name='ck_transcript_questions_question'),
        sa.CheckConstraint('answer IS NULL OR length(answer) <= 100000', name='ck_transcript_questions_answer'),
    )
    for column in ('video_id', 'revision_id', 'segment_id'):
        op.create_index(f'ix_transcript_questions_{column}', 'transcript_questions', [column])

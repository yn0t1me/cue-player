"""Store source preference and revision-bound Chinese translations without rebuilding parents.

Revision ID: 011_bilingual_subtitles
Revises: 010_saved_answer_history
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa

revision = '011_bilingual_subtitles'
down_revision = '010_saved_answer_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Inline CHECK is supported by SQLite ADD COLUMN. Do not batch-rebuild videos
    # or segments: their existing children include RESTRICT and CASCADE references.
    op.add_column('videos', sa.Column(
        'subtitle_preference', sa.String(12),
        sa.CheckConstraint("subtitle_preference IN ('manual_first', 'auto_only')",
                           name='video_subtitle_preference'),
        nullable=False, server_default='manual_first'))
    op.add_column('learning_transcript_segments', sa.Column(
        'translation_zh', sa.Text(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    if (connection.scalar(sa.text(
            'SELECT COUNT(*) FROM learning_transcript_segments WHERE translation_zh IS NOT NULL'))
            or connection.scalar(sa.text(
                "SELECT COUNT(*) FROM videos WHERE subtitle_preference != 'manual_first'"))):
        raise RuntimeError('Cannot downgrade while translations or source preferences exist')
    op.drop_column('learning_transcript_segments', 'translation_zh')
    op.drop_column('videos', 'subtitle_preference')

"""Remember first saved answers without restoring historical canceled favorites.

Revision ID: 010_saved_answer_history
Revises: 009_notes_experience
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = '010_saved_answer_history'
down_revision = '009_notes_experience'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('transcript_questions', sa.Column(
        'has_saved_answer', sa.Boolean(), nullable=False, server_default=sa.false()))
    # Preserve bodies/timestamps; SQLite trim differs for Unicode whitespace.
    connection = op.get_bind()
    rows = connection.execute(sa.text('SELECT id, answer FROM transcript_questions')).all()
    for question_id, answer in rows:
        if answer and answer.strip():
            connection.execute(sa.text(
                'UPDATE transcript_questions SET has_saved_answer = 1 WHERE id = :id'),
                {'id': question_id})


def downgrade() -> None:
    # A cleared answer still carries history; losing it could restore a canceled
    # favorite after upgrading and saving that same answer again.
    if op.get_bind().scalar(sa.text(
            'SELECT COUNT(*) FROM transcript_questions WHERE has_saved_answer = 1')):
        raise RuntimeError('Cannot downgrade while questions or answers exist with saved-answer history')
    op.drop_column('transcript_questions', 'has_saved_answer')

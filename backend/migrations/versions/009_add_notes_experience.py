"""Preserve historical favorites and add manually saved questions/answers.

Revision ID: 009_notes_experience
Revises: 008_source_aligned_learning
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa

revision = '009_notes_experience'
down_revision = '008_source_aligned_learning'
branch_labels = None
depends_on = None


def _anchor_columns():
    return [
        sa.Column('video_id', sa.String(36), nullable=False),
        sa.Column('revision_id', sa.String(36), nullable=False),
        sa.Column('segment_id', sa.String(36), nullable=False),
        sa.Column('start_offset', sa.Integer(), nullable=False),
        sa.Column('end_offset', sa.Integer(), nullable=False),
    ]


def _anchor_foreign_keys(table):
    return [sa.ForeignKeyConstraint([field], [f'{parent}.id'],
                                   name=f'fk_{table}_{field}_{parent}', ondelete='RESTRICT')
            for field, parent in [('video_id', 'videos'), ('revision_id', 'transcript_revisions'),
                                  ('segment_id', 'learning_transcript_segments')]]


def upgrade() -> None:
    op.create_table(
        'transcript_questions', *_anchor_columns(),
        sa.Column('selected_text', sa.Text(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.CheckConstraint('start_offset >= 0', name='ck_transcript_questions_start_offset'),
        sa.CheckConstraint('end_offset > start_offset', name='ck_transcript_questions_end_offset'),
        sa.CheckConstraint('length(trim(selected_text)) > 0',
                           name='ck_transcript_questions_selected_text'),
        sa.CheckConstraint('length(trim(question)) > 0 AND length(question) <= 10000',
                           name='ck_transcript_questions_question'),
        sa.CheckConstraint('answer IS NULL OR length(answer) <= 100000',
                           name='ck_transcript_questions_answer'),
        *_anchor_foreign_keys('transcript_questions'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_questions'))
    for field in ('video_id', 'revision_id', 'segment_id'):
        op.create_index(f'ix_transcript_questions_{field}', 'transcript_questions', [field])
    op.create_table(
        'transcript_mark_keys', *_anchor_columns(),
        sa.Column('mark_id', sa.String(36), nullable=False),
        *_anchor_foreign_keys('transcript_mark_keys'),
        sa.ForeignKeyConstraint(['mark_id'], ['transcript_marks.id'],
                                name='fk_transcript_mark_keys_mark_id_transcript_marks',
                                ondelete='RESTRICT'),
        sa.UniqueConstraint('mark_id', name='uq_transcript_mark_keys_mark_id'),
        sa.PrimaryKeyConstraint('video_id', 'revision_id', 'segment_id',
                                'start_offset', 'end_offset', name='pk_transcript_mark_keys'))
    # Python whitespace semantics match the API, including tabs/newlines/Unicode spaces.
    rows = op.get_bind().execute(sa.text(
        'SELECT * FROM transcript_marks ORDER BY created_at, id')).mappings().all()
    keys = {}
    fields = ('video_id', 'revision_id', 'segment_id', 'start_offset', 'end_offset')
    for row in rows:
        key = tuple(row[field] for field in fields)
        prior = keys.get(key)
        if prior is None or (not (prior['note'] and prior['note'].strip())
                             and row['note'] and row['note'].strip()):
            keys[key] = row
    for row in keys.values():
        op.get_bind().execute(sa.text(
            'INSERT INTO transcript_mark_keys '
            '(video_id, revision_id, segment_id, start_offset, end_offset, mark_id) '
            'VALUES (:video_id, :revision_id, :segment_id, :start_offset, :end_offset, :mark_id)'),
            {**{field: row[field] for field in fields}, 'mark_id': row['id']})


def downgrade() -> None:
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM transcript_questions')):
        raise RuntimeError('Cannot downgrade while transcript questions or answers exist')
    op.drop_table('transcript_mark_keys')
    op.drop_table('transcript_questions')

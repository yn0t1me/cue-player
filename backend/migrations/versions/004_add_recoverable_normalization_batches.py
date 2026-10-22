"""add recoverable normalization batch evidence

Revision ID: 004_add_recoverable_batches
Revises: 003_allow_faithful_repair_version
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004_add_recoverable_batches'
down_revision: Union[str, Sequence[str], None] = '003_allow_faithful_repair_version'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_run_foreign_keys() -> None:
    with op.batch_alter_table('transcript_corrections') as batch_op:
        batch_op.drop_constraint(
            'fk_transcript_corrections_learning_segment_id_learning_transcript_segments',
            type_='foreignkey')
        batch_op.drop_constraint(
            'fk_transcript_corrections_normalization_run_id_transcript_normalization_runs',
            type_='foreignkey')
    with op.batch_alter_table('learning_transcript_segments') as batch_op:
        batch_op.drop_constraint(
            'fk_learning_transcript_segments_normalization_run_id_transcript_normalization_runs',
            type_='foreignkey')


def _restore_run_foreign_keys() -> None:
    with op.batch_alter_table('learning_transcript_segments') as batch_op:
        batch_op.create_foreign_key(
            'fk_learning_transcript_segments_normalization_run_id_transcript_normalization_runs',
            'transcript_normalization_runs', ['normalization_run_id'], ['id'],
            ondelete='RESTRICT')
    with op.batch_alter_table('transcript_corrections') as batch_op:
        batch_op.create_foreign_key(
            'fk_transcript_corrections_learning_segment_id_learning_transcript_segments',
            'learning_transcript_segments', ['learning_segment_id'], ['id'],
            ondelete='RESTRICT')
        batch_op.create_foreign_key(
            'fk_transcript_corrections_normalization_run_id_transcript_normalization_runs',
            'transcript_normalization_runs', ['normalization_run_id'], ['id'],
            ondelete='RESTRICT')


def upgrade() -> None:
    _drop_run_foreign_keys()
    with op.batch_alter_table('transcript_normalization_runs') as batch_op:
        batch_op.add_column(sa.Column(
            'recovery_status', sa.String(), nullable=False,
            server_default=sa.text("'completed'")))
        batch_op.add_column(sa.Column('active_batch_index', sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            'ck_transcript_normalization_runs_recovery_status',
            "recovery_status IN ('running', 'needs_retry', 'completed')")
        batch_op.create_check_constraint(
            'ck_transcript_normalization_runs_active_batch',
            'active_batch_index IS NULL OR active_batch_index >= 0')
    _restore_run_foreign_keys()

    op.create_table(
        'transcript_normalization_batches',
        sa.Column('normalization_run_id', sa.String(length=36), nullable=False),
        sa.Column('batch_index', sa.Integer(), nullable=False),
        sa.Column('start_unit_index', sa.Integer(), nullable=False),
        sa.Column('end_unit_index', sa.Integer(), nullable=False),
        sa.Column('accept_end_unit_index', sa.Integer(), nullable=True),
        sa.Column('start_seconds', sa.Float(), nullable=True),
        sa.Column('end_seconds', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('request_payload', sa.JSON(none_as_null=True), nullable=False),
        sa.Column('candidate_payload', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('attempts', sa.JSON(none_as_null=True), nullable=False),
        sa.Column('failure_code', sa.String(), nullable=True),
        sa.Column('failure_rule', sa.String(), nullable=True),
        sa.Column('output_text', sa.Text(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.CheckConstraint('batch_index >= 0', name='ck_normalization_batches_index'),
        sa.CheckConstraint(
            'start_unit_index >= 0 AND end_unit_index > start_unit_index',
            name='ck_normalization_batches_range'),
        sa.CheckConstraint(
            '(start_seconds IS NULL AND end_seconds IS NULL) OR '
            '(start_seconds >= 0 AND end_seconds >= start_seconds)',
            name='ck_normalization_batches_time'),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name='ck_normalization_batches_status'),
        sa.ForeignKeyConstraint(
            ['normalization_run_id'], ['transcript_normalization_runs.id'],
            name='fk_normalization_batches_run', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_normalization_batches'),
        sa.UniqueConstraint('normalization_run_id', 'batch_index',
                            name='uq_normalization_batches_run_index'),
    )
    op.create_index('ix_transcript_normalization_batches_normalization_run_id',
                    'transcript_normalization_batches', ['normalization_run_id'])


def downgrade() -> None:
    op.drop_index('ix_transcript_normalization_batches_normalization_run_id',
                  table_name='transcript_normalization_batches')
    op.drop_table('transcript_normalization_batches')
    _drop_run_foreign_keys()
    with op.batch_alter_table('transcript_normalization_runs') as batch_op:
        batch_op.drop_constraint(
            'ck_transcript_normalization_runs_active_batch', type_='check')
        batch_op.drop_constraint(
            'ck_transcript_normalization_runs_recovery_status', type_='check')
        batch_op.drop_column('active_batch_index')
        batch_op.drop_column('recovery_status')
    _restore_run_foreign_keys()

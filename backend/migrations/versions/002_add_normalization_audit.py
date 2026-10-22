"""add normalization run and correction audit data

Revision ID: 002_add_normalization_audit
Revises: 001_create_m0_tables
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002_add_normalization_audit'
down_revision: Union[str, Sequence[str], None] = '001_create_m0_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'transcript_normalization_runs',
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('method', sa.String(), nullable=False),
        sa.Column('normalization_version', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(), nullable=True),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('prompt_version', sa.String(), nullable=True),
        sa.Column('input_unit_count', sa.Integer(), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('elapsed_ms', sa.Integer(), nullable=True),
        sa.Column('fallback_reason_code', sa.String(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.CheckConstraint(
            "method IN ('llm', 'deterministic', 'deterministic_fallback')",
            name='ck_transcript_normalization_runs_method'),
        sa.CheckConstraint(
            "(method = 'llm' AND normalization_version = 3 "
            "AND length(trim(provider)) > 0 AND length(trim(model)) > 0 "
            "AND length(trim(prompt_version)) > 0 AND request_count > 0 "
            "AND fallback_reason_code IS NULL) OR "
            "(method = 'deterministic' AND normalization_version = 2 "
            "AND provider IS NULL AND model IS NULL AND prompt_version IS NULL "
            "AND request_count = 0 AND input_tokens IS NULL AND output_tokens IS NULL "
            "AND elapsed_ms IS NULL AND fallback_reason_code IS NULL) OR "
            "(method = 'deterministic_fallback' AND normalization_version = 2 "
            "AND length(trim(provider)) > 0 AND length(trim(model)) > 0 "
            "AND length(trim(prompt_version)) > 0 "
            "AND length(trim(fallback_reason_code)) > 0)",
            name='ck_transcript_normalization_runs_method_evidence'),
        sa.CheckConstraint('input_unit_count > 0',
                           name='ck_transcript_normalization_runs_units'),
        sa.CheckConstraint('request_count >= 0',
                           name='ck_transcript_normalization_runs_requests'),
        sa.CheckConstraint(
            '(input_tokens IS NULL AND output_tokens IS NULL) OR '
            '(input_tokens >= 0 AND output_tokens >= 0)',
            name='ck_transcript_normalization_runs_usage'),
        sa.CheckConstraint('elapsed_ms IS NULL OR elapsed_ms >= 0',
                           name='ck_transcript_normalization_runs_elapsed'),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'],
                                name='fk_transcript_normalization_runs_job_id_processing_jobs',
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'],
                                name='fk_transcript_normalization_runs_video_id_videos',
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_normalization_runs'),
        sa.UniqueConstraint('job_id', name='uq_transcript_normalization_runs_job_id'),
    )
    op.create_index('ix_transcript_normalization_runs_video_id',
                    'transcript_normalization_runs', ['video_id'], unique=False)

    with op.batch_alter_table('learning_transcript_segments') as batch_op:
        batch_op.add_column(sa.Column('normalization_run_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            'fk_learning_transcript_segments_normalization_run_id_transcript_normalization_runs',
            'transcript_normalization_runs', ['normalization_run_id'], ['id'],
            ondelete='RESTRICT')
        batch_op.create_index('ix_learning_transcript_segments_normalization_run_id',
                              ['normalization_run_id'], unique=False)

    op.create_table(
        'transcript_corrections',
        sa.Column('normalization_run_id', sa.String(length=36), nullable=False),
        sa.Column('learning_segment_id', sa.String(length=36), nullable=False),
        sa.Column('sequence_index', sa.Integer(), nullable=False),
        sa.Column('source_ref_type', sa.String(), nullable=False),
        sa.Column('source_refs', sa.JSON(none_as_null=True), nullable=False),
        sa.Column('original_text', sa.Text(), nullable=False),
        sa.Column('corrected_text', sa.Text(), nullable=False),
        sa.Column('reason_code', sa.String(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.CheckConstraint('sequence_index >= 0', name='ck_transcript_corrections_sequence'),
        sa.CheckConstraint("source_ref_type IN ('word', 'cue_token')",
                           name='ck_transcript_corrections_source_ref_type'),
        sa.CheckConstraint("reason_code = 'contextual_transcript_correction'",
                           name='ck_transcript_corrections_reason_code'),
        sa.CheckConstraint(
            'length(trim(original_text)) > 0 AND '
            'length(trim(corrected_text)) > 0 AND length(trim(reason)) > 0',
            name='ck_transcript_corrections_text'),
        sa.ForeignKeyConstraint(
            ['learning_segment_id'], ['learning_transcript_segments.id'],
            name='fk_transcript_corrections_learning_segment_id_learning_transcript_segments',
            ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(
            ['normalization_run_id'], ['transcript_normalization_runs.id'],
            name='fk_transcript_corrections_normalization_run_id_transcript_normalization_runs',
            ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_corrections'),
        sa.UniqueConstraint('normalization_run_id', 'sequence_index',
                            name='uq_transcript_corrections_run_sequence'),
    )
    op.create_index('ix_transcript_corrections_learning_segment_id',
                    'transcript_corrections', ['learning_segment_id'], unique=False)
    op.create_index('ix_transcript_corrections_normalization_run_id',
                    'transcript_corrections', ['normalization_run_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_transcript_corrections_normalization_run_id',
                  table_name='transcript_corrections')
    op.drop_index('ix_transcript_corrections_learning_segment_id',
                  table_name='transcript_corrections')
    op.drop_table('transcript_corrections')

    with op.batch_alter_table('learning_transcript_segments') as batch_op:
        batch_op.drop_index('ix_learning_transcript_segments_normalization_run_id')
        batch_op.drop_constraint(
            'fk_learning_transcript_segments_normalization_run_id_transcript_normalization_runs',
            type_='foreignkey')
        batch_op.drop_column('normalization_run_id')

    op.drop_index('ix_transcript_normalization_runs_video_id',
                  table_name='transcript_normalization_runs')
    op.drop_table('transcript_normalization_runs')

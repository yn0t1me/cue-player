"""allow faithful transcript repair normalization version

Revision ID: 003_allow_faithful_repair_version
Revises: 002_add_normalization_audit
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '003_allow_faithful_repair_version'
down_revision: Union[str, Sequence[str], None] = '002_add_normalization_audit'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COMMON_EVIDENCE = (
    "AND length(trim(provider)) > 0 AND length(trim(model)) > 0 "
    "AND length(trim(prompt_version)) > 0 AND request_count > 0 "
    "AND fallback_reason_code IS NULL"
)


def _method_evidence_constraint(llm_versions: str) -> str:
    return (
        f"(method = 'llm' AND normalization_version {llm_versions} "
        f"{_COMMON_EVIDENCE}) OR "
        "(method = 'deterministic' AND normalization_version = 2 "
        "AND provider IS NULL AND model IS NULL AND prompt_version IS NULL "
        "AND request_count = 0 AND input_tokens IS NULL AND output_tokens IS NULL "
        "AND elapsed_ms IS NULL AND fallback_reason_code IS NULL) OR "
        "(method = 'deterministic_fallback' AND normalization_version = 2 "
        "AND length(trim(provider)) > 0 AND length(trim(model)) > 0 "
        "AND length(trim(prompt_version)) > 0 "
        "AND length(trim(fallback_reason_code)) > 0)"
    )


def _replace_method_evidence_constraint(llm_versions: str) -> None:
    with op.batch_alter_table('transcript_corrections') as batch_op:
        batch_op.drop_constraint(
            'fk_transcript_corrections_learning_segment_id_learning_transcript_segments',
            type_='foreignkey',
        )
        batch_op.drop_constraint(
            'fk_transcript_corrections_normalization_run_id_transcript_normalization_runs',
            type_='foreignkey',
        )
    with op.batch_alter_table('learning_transcript_segments') as batch_op:
        batch_op.drop_constraint(
            'fk_learning_transcript_segments_normalization_run_id_transcript_normalization_runs',
            type_='foreignkey',
        )
    with op.batch_alter_table('transcript_normalization_runs') as batch_op:
        batch_op.drop_constraint(
            'ck_transcript_normalization_runs_method_evidence', type_='check')
        batch_op.create_check_constraint(
            'ck_transcript_normalization_runs_method_evidence',
            _method_evidence_constraint(llm_versions),
        )
    with op.batch_alter_table('learning_transcript_segments') as batch_op:
        batch_op.create_foreign_key(
            'fk_learning_transcript_segments_normalization_run_id_transcript_normalization_runs',
            'transcript_normalization_runs',
            ['normalization_run_id'],
            ['id'],
            ondelete='RESTRICT',
        )
    with op.batch_alter_table('transcript_corrections') as batch_op:
        batch_op.create_foreign_key(
            'fk_transcript_corrections_learning_segment_id_learning_transcript_segments',
            'learning_transcript_segments',
            ['learning_segment_id'],
            ['id'],
            ondelete='RESTRICT',
        )
        batch_op.create_foreign_key(
            'fk_transcript_corrections_normalization_run_id_transcript_normalization_runs',
            'transcript_normalization_runs',
            ['normalization_run_id'],
            ['id'],
            ondelete='RESTRICT',
        )


def upgrade() -> None:
    _replace_method_evidence_constraint('IN (3, 4)')


def downgrade() -> None:
    _replace_method_evidence_constraint('= 3')

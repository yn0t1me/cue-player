"""Allow source-timed learning without rewriting historical evidence.

Revision ID: 008_source_aligned_learning
Revises: 007_add_chunk_layouts
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = '008_source_aligned_learning'
down_revision = '007_add_chunk_layouts'
branch_labels = None
depends_on = None

# SQLite batch replacement must first detach every incoming RESTRICT reference.
# Preserve their names/options, including the layout -> boundaries CASCADE:
# leaving that reference attached would erase boundaries during table replacement.
_CHILDREN = ('transcript_marks', 'transcript_chunk_segments', 'transcript_corrections',
             'transcript_chunk_layouts', 'learning_transcript_segments')
_PARENTS = {'transcript_revisions', 'learning_transcript_segments', 'transcript_chunk_layouts'}


def _replace_constraints(origin_rule: str, version_rule: str) -> None:
    inspector = sa.inspect(op.get_bind())
    references = {table: [fk for fk in inspector.get_foreign_keys(table)
                          if fk['referred_table'] in _PARENTS] for table in _CHILDREN}
    for table, keys in references.items():
        if keys:
            with op.batch_alter_table(table) as batch:
                for fk in keys:
                    batch.drop_constraint(fk['name'], type_='foreignkey')
    with op.batch_alter_table('transcript_revisions') as batch:
        batch.drop_constraint('ck_transcript_revisions_origin', type_='check')
        batch.create_check_constraint('ck_transcript_revisions_origin', origin_rule)
    with op.batch_alter_table('learning_transcript_segments') as batch:
        batch.drop_constraint('ck_learning_transcript_segments_version', type_='check')
        batch.create_check_constraint('ck_learning_transcript_segments_version', version_rule)
    for table in reversed(_CHILDREN):
        if references[table]:
            with op.batch_alter_table(table) as batch:
                for fk in references[table]:
                    batch.create_foreign_key(fk['name'], fk['referred_table'],
                                             fk['constrained_columns'], fk['referred_columns'],
                                             **fk['options'])


def upgrade() -> None:
    _replace_constraints(
        "origin IN ('generated', 'external_srt', 'source_aligned')",
        "(normalization_version IS NOT NULL AND normalization_version >= 1 "
        "AND source_ref_type NOT IN ('external_srt', 'source_units')) OR "
        "(normalization_version IS NULL AND source_ref_type IN ('external_srt', 'source_units'))")


def downgrade() -> None:
    connection = op.get_bind()
    if (connection.scalar(sa.text(
            "SELECT COUNT(*) FROM transcript_revisions WHERE origin = 'source_aligned'"))
            or connection.scalar(sa.text(
                "SELECT COUNT(*) FROM learning_transcript_segments WHERE source_ref_type = 'source_units'"))):
        raise RuntimeError('Cannot downgrade while source-aligned learning exists')
    _replace_constraints(
        "origin IN ('generated', 'external_srt')",
        "(normalization_version >= 1 AND source_ref_type != 'external_srt') OR "
        "(normalization_version IS NULL AND source_ref_type = 'external_srt')")

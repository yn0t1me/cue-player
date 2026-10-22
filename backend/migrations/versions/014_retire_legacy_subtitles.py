"""Retire legacy cloud normalization storage and SRT-only revisions.

Revision ID: 014_retire_legacy_subtitles
Revises: 013_import_retries
Create Date: 2026-10-21

Upgrade refuses unremoved legacy records before changing any schema. User data
cleanup is a separate, backed-up maintenance action; future histories are kept.
Downgrade restores empty legacy tables, never the deleted contents.
"""
from alembic import op
import sqlalchemy as sa

revision = '014_retire_legacy_subtitles'
down_revision = '013_import_retries'
branch_labels = None
depends_on = None

NEW_ORIGIN = "origin IN ('generated', 'source_aligned')"
OLD_ORIGIN = "origin IN ('generated', 'external_srt', 'source_aligned')"
NEW_VERSION = ("(normalization_version IS NOT NULL AND normalization_version = 2 "
               "AND source_ref_type = 'cue') OR "
               "(normalization_version IS NULL AND source_ref_type = 'source_units')")
OLD_VERSION = ("(normalization_version IS NOT NULL AND normalization_version >= 1 "
               "AND source_ref_type NOT IN ('external_srt', 'source_units')) OR "
               "(normalization_version IS NULL AND source_ref_type IN ('external_srt', 'source_units'))")
NEW_CHECKS = [
    ('ck_transcript_normalization_runs_method', "method = 'deterministic'"),
    ('ck_transcript_normalization_runs_version', 'normalization_version = 2'),
    ('ck_transcript_normalization_runs_units', 'input_unit_count > 0'),
]
OLD_CHECKS = [('ck_transcript_normalization_runs_method',
  "method IN ('llm', 'deterministic', 'deterministic_fallback')"),
 ('ck_transcript_normalization_runs_method_evidence',
  "(method = 'llm' AND normalization_version IN (3, 4) AND length(trim(provider)) > 0 AND "
  'length(trim(model)) > 0 AND length(trim(prompt_version)) > 0 AND request_count > 0 AND '
  "fallback_reason_code IS NULL) OR (method = 'deterministic' AND normalization_version = 2 AND "
  'provider IS NULL AND model IS NULL AND prompt_version IS NULL AND request_count = 0 AND '
  'input_tokens IS NULL AND output_tokens IS NULL AND elapsed_ms IS NULL AND fallback_reason_code '
  "IS NULL) OR (method = 'deterministic_fallback' AND normalization_version = 2 AND "
  'length(trim(provider)) > 0 AND length(trim(model)) > 0 AND length(trim(prompt_version)) > 0 AND '
  'length(trim(fallback_reason_code)) > 0)'),
 ('ck_transcript_normalization_runs_units', 'input_unit_count > 0'),
 ('ck_transcript_normalization_runs_requests', 'request_count >= 0'),
 ('ck_transcript_normalization_runs_usage',
  '(input_tokens IS NULL AND output_tokens IS NULL) OR (input_tokens >= 0 AND output_tokens >= 0)'),
 ('ck_transcript_normalization_runs_elapsed', 'elapsed_ms IS NULL OR elapsed_ms >= 0'),
 ('ck_transcript_normalization_runs_recovery_status',
  "recovery_status IN ('running', 'needs_retry', 'completed')"),
 ('ck_transcript_normalization_runs_active_batch',
  'active_batch_index IS NULL OR active_batch_index >= 0')]

LEGACY_COLUMNS = [
    ('provider', sa.String(), True, None),
    ('model', sa.String(), True, None),
    ('prompt_version', sa.String(), True, None),
    ('request_count', sa.Integer(), False, '0'),
    ('input_tokens', sa.Integer(), True, None),
    ('output_tokens', sa.Integer(), True, None),
    ('elapsed_ms', sa.Integer(), True, None),
    ('fallback_reason_code', sa.String(), True, None),
    ('recovery_status', sa.String(), False, 'completed'),
    ('active_batch_index', sa.Integer(), True, None),
]


def _rewrite(upgrading: bool) -> None:
    # Detach all incoming references before SQLite batch replacement, including
    # transitive children (favorite keys and boundaries). Never disable FKs or
    # let a CASCADE erase children while replacing a parent table.
    inspector = sa.inspect(op.get_bind())
    keys = {table: inspector.get_foreign_keys(table)
            for table in inspector.get_table_names() if table != 'alembic_version'}
    affected = {'transcript_normalization_runs', 'transcript_revisions',
                'learning_transcript_segments'}
    while True:
        children = {table for table, fks in keys.items()
                    if any(fk['referred_table'] in affected for fk in fks)}
        if children <= affected:
            break
        affected.update(children)
    populated = any(op.get_bind().scalar(sa.text('SELECT 1 FROM "' + table + '" LIMIT 1'))
                    for table in affected)
    # Empty installations have no children to lose and no RESTRICT rows. Their
    # existing FK declarations can remain while replacing the three empty roots.
    references = {table: [fk for fk in keys[table] if fk['referred_table'] in affected]
                  if populated else [] for table in affected}
    pending = set(affected)
    order = []
    while pending:
        referenced = {fk['referred_table'] for table in pending
                      for fk in references[table]}
        leaves = sorted(pending - referenced)
        if not leaves:
            raise RuntimeError('Cannot replace cyclic subtitle foreign keys')
        order.extend(leaves)
        pending.difference_update(leaves)
    for table in order:
        if references[table]:
            with op.batch_alter_table(table) as batch:
                for fk in references[table]:
                    batch.drop_constraint(fk['name'], type_='foreignkey')
    with op.batch_alter_table('transcript_normalization_runs') as batch:
        for name, _ in OLD_CHECKS if upgrading else NEW_CHECKS:
            batch.drop_constraint(name, type_='check')
        for name, kind, nullable, default in LEGACY_COLUMNS:
            if upgrading:
                batch.drop_column(name)
            else:
                batch.add_column(sa.Column(name, kind, nullable=nullable, server_default=default))
        for name, rule in NEW_CHECKS if upgrading else OLD_CHECKS:
            batch.create_check_constraint(name, rule)
    if not upgrading:
        # The old request_count column had no default. Its temporary default
        # populated deterministic rows during ADD COLUMN only.
        with op.batch_alter_table('transcript_normalization_runs') as batch:
            batch.alter_column('request_count', server_default=None)
    with op.batch_alter_table('transcript_revisions') as batch:
        batch.drop_constraint('ck_transcript_revisions_origin', type_='check')
        batch.create_check_constraint('ck_transcript_revisions_origin',
                                      NEW_ORIGIN if upgrading else OLD_ORIGIN)
    with op.batch_alter_table('learning_transcript_segments') as batch:
        batch.drop_constraint('ck_learning_transcript_segments_version', type_='check')
        batch.create_check_constraint('ck_learning_transcript_segments_version',
                                      NEW_VERSION if upgrading else OLD_VERSION)
        batch.alter_column('normalization_version', server_default='2' if upgrading else '1')
    for table in reversed(order):
        if references[table]:
            with op.batch_alter_table(table) as batch:
                for fk in references[table]:
                    batch.create_foreign_key(fk['name'], fk['referred_table'],
                                             fk['constrained_columns'], fk['referred_columns'],
                                             **fk['options'])


def upgrade() -> None:
    connection = op.get_bind()
    guards = [
        'SELECT COUNT(*) FROM transcript_corrections',
        'SELECT COUNT(*) FROM transcript_normalization_batches',
        "SELECT COUNT(*) FROM transcript_normalization_runs WHERE method != 'deterministic' "
        "OR normalization_version != 2 OR recovery_status != 'completed' OR active_batch_index IS NOT NULL",
        "SELECT COUNT(*) FROM transcript_revisions WHERE origin = 'external_srt'",
        'SELECT COUNT(*) FROM learning_transcript_segments WHERE NOT (' + NEW_VERSION + ') '
        "OR (normalization_version IS NULL AND source_ref_type != 'source_units')",
    ]
    if any(connection.scalar(sa.text(query)) for query in guards):
        raise RuntimeError('Back up and remove retired subtitle records before migration 014')
    op.drop_table('transcript_corrections')
    op.drop_table('transcript_normalization_batches')
    _rewrite(True)


def downgrade() -> None:
    _rewrite(False)

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

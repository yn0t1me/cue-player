"""Add published transcript revisions without replacing historical segments.

Revision ID: 005_add_transcript_revisions
Revises: 004_add_recoverable_batches
Create Date: 2026-10-05
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = '005_add_transcript_revisions'
down_revision = '004_add_recoverable_batches'
branch_labels = None
depends_on = None


def _drop_correction_segment_fk() -> None:
    with op.batch_alter_table('transcript_corrections') as batch:
        batch.drop_constraint(
            'fk_transcript_corrections_learning_segment_id_learning_transcript_segments',
            type_='foreignkey')


def _restore_correction_segment_fk() -> None:
    with op.batch_alter_table('transcript_corrections') as batch:
        batch.create_foreign_key(
            'fk_transcript_corrections_learning_segment_id_learning_transcript_segments',
            'learning_transcript_segments', ['learning_segment_id'], ['id'],
            ondelete='RESTRICT')


def upgrade() -> None:
    op.create_table(
        'transcript_revisions',
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('origin', sa.String(), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('content_sha256', sa.String(length=64), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                  nullable=False),
        sa.CheckConstraint("origin IN ('generated', 'external_srt')",
                           name='ck_transcript_revisions_origin'),
        sa.CheckConstraint('revision_number >= 1', name='ck_transcript_revisions_number'),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'],
                                name='fk_transcript_revisions_video_id_videos',
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name='pk_transcript_revisions'),
        sa.UniqueConstraint('video_id', 'revision_number',
                            name='uq_transcript_revisions_video_number'),
    )
    op.create_index('ix_transcript_revisions_video_id', 'transcript_revisions', ['video_id'])
    op.add_column('videos', sa.Column('current_revision_id', sa.String(length=36), nullable=True))
    op.create_index('ix_videos_current_revision_id', 'videos', ['current_revision_id'])
    op.add_column('learning_transcript_segments', sa.Column(
        'revision_id', sa.String(length=36), nullable=True))

    connection = op.get_bind()
    existing = connection.execute(sa.text(
        'SELECT video_id, MIN(normalization_version) AS minimum_version, '
        'MAX(normalization_version) AS maximum_version, MIN(created_at) AS first_created '
        'FROM learning_transcript_segments GROUP BY video_id')).mappings().all()
    for item in existing:
        if item['minimum_version'] != item['maximum_version']:
            raise RuntimeError('Existing video has mixed Learning normalization versions')
        revision_id = str(uuid4())
        connection.execute(sa.text(
            'INSERT INTO transcript_revisions (id, video_id, origin, revision_number, created_at) '
            'VALUES (:id, :video_id, :origin, 1, :created_at)'),
            {'id': revision_id, 'video_id': item['video_id'], 'origin': 'generated',
             'created_at': item['first_created']})
        connection.execute(sa.text(
            'UPDATE learning_transcript_segments SET revision_id = :revision_id '
            'WHERE video_id = :video_id'),
            {'revision_id': revision_id, 'video_id': item['video_id']})
        connection.execute(sa.text(
            'UPDATE videos SET current_revision_id = :revision_id WHERE id = :video_id'),
            {'revision_id': revision_id, 'video_id': item['video_id']})

    _drop_correction_segment_fk()
    with op.batch_alter_table('learning_transcript_segments') as batch:
        batch.drop_constraint('uq_learning_transcript_segments_video_sequence', type_='unique')
        batch.create_unique_constraint('uq_learning_transcript_segments_revision_sequence',
                                       ['revision_id', 'sequence_index'])
        batch.alter_column('revision_id', existing_type=sa.String(length=36), nullable=False)
        batch.create_foreign_key(
            'fk_learning_transcript_segments_revision_id_transcript_revisions',
            'transcript_revisions', ['revision_id'], ['id'], ondelete='RESTRICT')
        batch.create_index('ix_learning_transcript_segments_revision_id', ['revision_id'])
        batch.alter_column('normalization_version', existing_type=sa.Integer(), nullable=True)
        batch.drop_constraint('ck_learning_transcript_segments_version', type_='check')
        batch.create_check_constraint('ck_learning_transcript_segments_version',
            "(normalization_version >= 1 AND source_ref_type != 'external_srt') OR "
            "(normalization_version IS NULL AND source_ref_type = 'external_srt')")
    _restore_correction_segment_fk()


def downgrade() -> None:
    connection = op.get_bind()
    external = connection.scalar(sa.text(
        "SELECT COUNT(*) FROM transcript_revisions WHERE origin = 'external_srt'"))
    if external:
        raise RuntimeError('Cannot downgrade while externally imported transcript revisions exist')

    _drop_correction_segment_fk()
    with op.batch_alter_table('learning_transcript_segments') as batch:
        batch.drop_index('ix_learning_transcript_segments_revision_id')
        batch.drop_constraint(
            'fk_learning_transcript_segments_revision_id_transcript_revisions',
            type_='foreignkey')
        batch.drop_constraint('uq_learning_transcript_segments_revision_sequence', type_='unique')
        batch.create_unique_constraint('uq_learning_transcript_segments_video_sequence',
                                       ['video_id', 'sequence_index'])
        batch.drop_constraint('ck_learning_transcript_segments_version', type_='check')
        batch.create_check_constraint('ck_learning_transcript_segments_version',
                                      'normalization_version >= 1')
        batch.alter_column('normalization_version', existing_type=sa.Integer(), nullable=False)
        batch.drop_column('revision_id')
    _restore_correction_segment_fk()
    op.drop_index('ix_videos_current_revision_id', table_name='videos')
    op.drop_column('videos', 'current_revision_id')
    op.drop_index('ix_transcript_revisions_video_id', table_name='transcript_revisions')
    op.drop_table('transcript_revisions')

"""add video collections and import batches

Revision ID: 012_video_collections
Revises: 011_bilingual_subtitles
Create Date: 2026-10-14 08:52:27.679477

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012_video_collections'
down_revision = '011_bilingual_subtitles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('video_collections',
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_playlist_id', sa.String(length=200), nullable=True),
        sa.Column('source_playlist_url', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('length(trim(name)) BETWEEN 1 AND 200', name='ck_video_collections_name'),
        sa.CheckConstraint('version >= 1', name='ck_video_collections_version'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_video_collections'))
    )
    op.create_table('video_import_previews',
        sa.Column('input_kind', sa.String(length=8), nullable=False),
        sa.Column('source', sa.JSON(), nullable=False),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('duplicate_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("input_kind IN ('single', 'multiple', 'playlist')", name='ck_video_import_previews_kind'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_video_import_previews'))
    )
    op.create_index(op.f('ix_video_import_previews_expires_at'), 'video_import_previews', ['expires_at'], unique=False)
    op.create_table('video_collection_items',
        sa.Column('collection_id', sa.String(length=36), nullable=False),
        sa.Column('video_id', sa.String(length=36), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('position >= 0', name='ck_video_collection_items_position'),
        sa.ForeignKeyConstraint(['collection_id'], ['video_collections.id'], name=op.f('fk_video_collection_items_collection_id_video_collections'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_video_collection_items_video_id_videos'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_video_collection_items')),
        sa.UniqueConstraint('collection_id', 'position', name='uq_video_collection_items_position'),
        sa.UniqueConstraint('collection_id', 'video_id', name=op.f('uq_video_collection_items_collection_id'))
    )
    op.create_index(op.f('ix_video_collection_items_collection_id'), 'video_collection_items', ['collection_id'], unique=False)
    op.create_index(op.f('ix_video_collection_items_video_id'), 'video_collection_items', ['video_id'], unique=False)
    op.create_table('video_import_batches',
        sa.Column('preview_id', sa.String(length=36), nullable=False),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('request_digest', sa.String(length=64), nullable=False),
        sa.Column('subtitle_preference', sa.String(length=12), nullable=False),
        sa.Column('collection_id', sa.String(length=36), nullable=True),
        sa.Column('collection_name_snapshot', sa.String(length=200), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("subtitle_preference IN ('manual_first', 'auto_only')", name='ck_video_import_batches_preference'),
        sa.ForeignKeyConstraint(['collection_id'], ['video_collections.id'], name=op.f('fk_video_import_batches_collection_id_video_collections'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['preview_id'], ['video_import_previews.id'], name=op.f('fk_video_import_batches_preview_id_video_import_previews'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_video_import_batches')),
        sa.UniqueConstraint('idempotency_key', name=op.f('uq_video_import_batches_idempotency_key'))
    )
    op.create_index(op.f('ix_video_import_batches_collection_id'), 'video_import_batches', ['collection_id'], unique=False)
    op.create_index(op.f('ix_video_import_batches_preview_id'), 'video_import_batches', ['preview_id'], unique=False)
    op.create_table('video_import_batch_items',
        sa.Column('batch_id', sa.String(length=36), nullable=False),
        sa.Column('preview_item_id', sa.String(length=36), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('youtube_video_id', sa.String(length=32), nullable=True),
        sa.Column('video_id', sa.String(length=36), nullable=True),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('disposition', sa.String(length=14), nullable=False),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("disposition IN ('created', 'reused', 'already_member', 'unavailable')", name='ck_video_import_batch_items_disposition'),
        sa.CheckConstraint('position >= 0', name='ck_video_import_batch_items_position'),
        sa.ForeignKeyConstraint(['batch_id'], ['video_import_batches.id'], name=op.f('fk_video_import_batch_items_batch_id_video_import_batches'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'], name=op.f('fk_video_import_batch_items_job_id_processing_jobs'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_video_import_batch_items_video_id_videos'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_video_import_batch_items')),
        sa.UniqueConstraint('batch_id', 'position', name='uq_video_import_batch_items_position'),
        sa.UniqueConstraint('batch_id', 'preview_item_id', name=op.f('uq_video_import_batch_items_batch_id'))
    )
    op.create_index(op.f('ix_video_import_batch_items_batch_id'), 'video_import_batch_items', ['batch_id'], unique=False)
    op.create_index(op.f('ix_video_import_batch_items_job_id'), 'video_import_batch_items', ['job_id'], unique=False)
    op.create_index(op.f('ix_video_import_batch_items_video_id'), 'video_import_batch_items', ['video_id'], unique=False)


def downgrade() -> None:
    """Refuse destructive rollback of collections or import history."""
    connection = op.get_bind()
    for table in ('video_collections', 'video_collection_items', 'video_import_previews',
                  'video_import_batches', 'video_import_batch_items'):
        if connection.scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('Cannot downgrade while collections or import history exist')
    op.drop_index(op.f('ix_video_import_batch_items_video_id'), table_name='video_import_batch_items')
    op.drop_index(op.f('ix_video_import_batch_items_job_id'), table_name='video_import_batch_items')
    op.drop_index(op.f('ix_video_import_batch_items_batch_id'), table_name='video_import_batch_items')
    op.drop_table('video_import_batch_items')
    op.drop_index(op.f('ix_video_import_batches_preview_id'), table_name='video_import_batches')
    op.drop_index(op.f('ix_video_import_batches_collection_id'), table_name='video_import_batches')
    op.drop_table('video_import_batches')
    op.drop_index(op.f('ix_video_collection_items_video_id'), table_name='video_collection_items')
    op.drop_index(op.f('ix_video_collection_items_collection_id'), table_name='video_collection_items')
    op.drop_table('video_collection_items')
    op.drop_index(op.f('ix_video_import_previews_expires_at'), table_name='video_import_previews')
    op.drop_table('video_import_previews')
    op.drop_table('video_collections')

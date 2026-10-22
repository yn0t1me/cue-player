"""persist import retry requests and bindings

Revision ID: 013_import_retries
Revises: 012_video_collections
Create Date: 2026-10-14 09:29:07.649926

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_import_retries'
down_revision = '012_video_collections'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('video_import_retry_requests',
        sa.Column('target_kind', sa.String(length=5), nullable=False),
        sa.Column('target_id', sa.String(length=36), nullable=False),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('request_digest', sa.String(length=64), nullable=False),
        sa.Column('response_payload', sa.JSON(), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("target_kind IN ('video', 'batch')", name='ck_video_import_retry_requests_kind'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_video_import_retry_requests')),
        sa.UniqueConstraint('target_kind', 'target_id', 'idempotency_key', name='uq_video_import_retry_requests_key')
    )
    op.create_table('video_import_retry_bindings',
        sa.Column('batch_item_id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['batch_item_id'], ['video_import_batch_items.id'], name=op.f('fk_video_import_retry_bindings_batch_item_id_video_import_batch_items'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'], name=op.f('fk_video_import_retry_bindings_job_id_processing_jobs'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('batch_item_id', name=op.f('pk_video_import_retry_bindings'))
    )
    op.create_index(op.f('ix_video_import_retry_bindings_job_id'), 'video_import_retry_bindings', ['job_id'], unique=False)


def downgrade() -> None:
    """Retain accepted retry history and bindings."""
    for table in ('video_import_retry_requests', 'video_import_retry_bindings'):
        if op.get_bind().scalar(sa.text(f'SELECT COUNT(*) FROM {table}')):
            raise RuntimeError('Cannot downgrade while import retry history exists')
    op.drop_index(op.f('ix_video_import_retry_bindings_job_id'), table_name='video_import_retry_bindings')
    op.drop_table('video_import_retry_bindings')
    op.drop_table('video_import_retry_requests')

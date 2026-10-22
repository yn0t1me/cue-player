from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdentityCreated, Updated, UTCDateTime


class VideoCollection(IdentityCreated, Updated, Base):
    __tablename__ = 'video_collections'
    __table_args__ = (
        CheckConstraint('length(trim(name)) BETWEEN 1 AND 200', name='ck_video_collections_name'),
        CheckConstraint('version >= 1', name='ck_video_collections_version'),
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    source_playlist_id: Mapped[str | None] = mapped_column(String(200))
    source_playlist_url: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(server_default='1')


class VideoCollectionItem(IdentityCreated, Base):
    __tablename__ = 'video_collection_items'
    __table_args__ = (
        UniqueConstraint('collection_id', 'video_id'),
        UniqueConstraint('collection_id', 'position', name='uq_video_collection_items_position'),
        CheckConstraint('position >= 0', name='ck_video_collection_items_position'),
    )
    collection_id: Mapped[str] = mapped_column(ForeignKey('video_collections.id', ondelete='CASCADE'), index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    position: Mapped[int]


class VideoImportPreview(IdentityCreated, Base):
    __tablename__ = 'video_import_previews'
    __table_args__ = (CheckConstraint("input_kind IN ('single', 'multiple', 'playlist')", name='ck_video_import_previews_kind'),)
    input_kind: Mapped[str] = mapped_column(String(8))
    source: Mapped[dict] = mapped_column(JSON)
    items: Mapped[list] = mapped_column(JSON)
    duplicate_count: Mapped[int] = mapped_column(server_default='0')
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class VideoImportBatch(IdentityCreated, Base):
    __tablename__ = 'video_import_batches'
    __table_args__ = (CheckConstraint("subtitle_preference IN ('manual_first', 'auto_only')", name='ck_video_import_batches_preference'),)
    preview_id: Mapped[str] = mapped_column(ForeignKey('video_import_previews.id', ondelete='RESTRICT'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    request_digest: Mapped[str] = mapped_column(String(64))
    subtitle_preference: Mapped[str] = mapped_column(String(12))
    collection_id: Mapped[str | None] = mapped_column(ForeignKey('video_collections.id', ondelete='SET NULL'), index=True)
    collection_name_snapshot: Mapped[str | None] = mapped_column(String(200))


class VideoImportBatchItem(IdentityCreated, Base):
    __tablename__ = 'video_import_batch_items'
    __table_args__ = (
        UniqueConstraint('batch_id', 'preview_item_id'),
        UniqueConstraint('batch_id', 'position', name='uq_video_import_batch_items_position'),
        CheckConstraint('position >= 0', name='ck_video_import_batch_items_position'),
        CheckConstraint("disposition IN ('created', 'reused', 'already_member', 'unavailable')", name='ck_video_import_batch_items_disposition'),
    )
    batch_id: Mapped[str] = mapped_column(ForeignKey('video_import_batches.id', ondelete='CASCADE'), index=True)
    preview_item_id: Mapped[str] = mapped_column(String(36))
    position: Mapped[int]
    youtube_video_id: Mapped[str | None] = mapped_column(String(32))
    video_id: Mapped[str | None] = mapped_column(ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey('processing_jobs.id', ondelete='RESTRICT'), index=True)
    disposition: Mapped[str] = mapped_column(String(14))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)


class VideoImportRetryRequest(IdentityCreated, Base):
    __tablename__ = 'video_import_retry_requests'
    __table_args__ = (
        UniqueConstraint('target_kind', 'target_id', 'idempotency_key', name='uq_video_import_retry_requests_key'),
        CheckConstraint("target_kind IN ('video', 'batch')", name='ck_video_import_retry_requests_kind'),
    )
    target_kind: Mapped[str] = mapped_column(String(5))
    target_id: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    response_payload: Mapped[dict] = mapped_column(JSON)


class VideoImportRetryBinding(Base):
    __tablename__ = 'video_import_retry_bindings'
    batch_item_id: Mapped[str] = mapped_column(
        ForeignKey('video_import_batch_items.id', ondelete='CASCADE'), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('processing_jobs.id', ondelete='RESTRICT'), index=True)

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import JobStatus, ProcessingStage
from app.db.base import Base, IdentityCreated, Updated, UTCDateTime, enum_column


class ProcessingJob(IdentityCreated, Updated, Base):
    __tablename__ = 'processing_jobs'
    __table_args__ = (CheckConstraint('progress >= 0 AND progress <= 100', name='ck_processing_jobs_progress'),)

    video_id: Mapped[str] = mapped_column(ForeignKey('videos.id', ondelete='RESTRICT'), index=True)
    stage: Mapped[ProcessingStage] = mapped_column(enum_column(ProcessingStage, 'processing_stage'))
    status: Mapped[JobStatus] = mapped_column(enum_column(JobStatus, 'job_status'), server_default='pending')
    progress: Mapped[int] = mapped_column(server_default='0')
    error_code: Mapped[str | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

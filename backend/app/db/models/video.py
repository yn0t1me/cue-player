from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import SubtitlePreference, SubtitleSource, VideoStatus
from app.db.base import Base, IdentityCreated, Updated, enum_column


class Video(IdentityCreated, Updated, Base):
    __tablename__ = 'videos'

    youtube_video_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    youtube_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    channel_title: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[float | None]
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[VideoStatus] = mapped_column(enum_column(VideoStatus, 'video_status'), server_default='processing')
    subtitle_source: Mapped[SubtitleSource | None] = mapped_column(enum_column(SubtitleSource, 'video_subtitle_source'))
    subtitle_preference: Mapped[SubtitlePreference] = mapped_column(
        enum_column(SubtitlePreference, 'video_subtitle_preference'), server_default='manual_first')
    subtitle_language: Mapped[str | None]
    current_revision_id: Mapped[str | None] = mapped_column(String(36), index=True)

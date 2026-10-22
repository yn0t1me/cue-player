from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import SubtitlePreference, JobStatus, ProcessingStage, SubtitleSource, VideoStatus


class ImportVideoRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    url: str = Field(min_length=1, max_length=2048)
    subtitle_preference: SubtitlePreference = SubtitlePreference.MANUAL_FIRST


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    stage: ProcessingStage
    status: JobStatus
    progress: int
    error_code: str | None = None
    error_message: str | None = None


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    youtube_video_id: str
    youtube_url: str
    title: str | None
    channel_title: str | None
    duration_seconds: float | None
    thumbnail_url: str | None
    status: VideoStatus
    subtitle_preference: SubtitlePreference
    subtitle_source: SubtitleSource | None
    subtitle_language: str | None
    created_at: datetime
    processing: ProcessingJobResponse | None = None


class ImportVideoResponse(BaseModel):
    already_exists: bool
    video: VideoResponse
    job: ProcessingJobResponse | None


class VideoListResponse(BaseModel):
    items: list[VideoResponse]

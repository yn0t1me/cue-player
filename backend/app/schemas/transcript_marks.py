from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TranscriptSelectionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    revision_id: str = Field(min_length=1, max_length=36)
    segment_id: str = Field(min_length=1, max_length=36)
    start_offset: int = Field(ge=0, le=1_000_000)
    end_offset: int = Field(gt=0, le=1_000_000)
    selected_text: str = Field(min_length=1)


class CreateTranscriptMarkRequest(TranscriptSelectionRequest):
    note: str | None = Field(default=None, max_length=10_000)


class UpdateTranscriptMarkRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    note: str | None = Field(max_length=10_000)


class TranscriptAnchorResponse(BaseModel):
    id: str
    video_id: str
    revision_id: str
    revision_number: int
    revision_origin: str
    is_current: bool
    segment_id: str
    segment_sequence_index: int
    segment_start: float
    segment_end: float
    segment_text: str
    start_offset: int
    end_offset: int
    selected_text: str
    created_at: datetime
    updated_at: datetime


class TranscriptMarkResponse(TranscriptAnchorResponse):
    note: str | None


class TranscriptMarkListResponse(BaseModel):
    items: list[TranscriptMarkResponse]

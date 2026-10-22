from pydantic import BaseModel


class TranscriptSegmentResponse(BaseModel):
    id: str
    sequence_index: int
    start: float
    end: float
    text: str
    translation_zh: str | None = None


class TranscriptResponse(BaseModel):
    video_id: str
    revision_id: str
    origin: str
    normalization_version: int | None
    segments: list[TranscriptSegmentResponse]
